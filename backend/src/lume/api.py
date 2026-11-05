import json
from datetime import timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError

from .agent import TERMINAL
from .config import Settings
from .db import database
from .knowledge import current_message, ingest, message_view
from .models import (
    Answer,
    Grant,
    ImageAsset,
    Message,
    Observation,
    Principal,
    ProcessingJob,
    Space,
    Task,
    TaskEvent,
    now,
)
from .providers import provider_for
from .qq import authorize_path, handle_event, key_for, verify_signature
from .schemas import GrantInput, ImportInput, SpaceInput, TaskInput
from .security import DomainError, authenticate, check_dependencies, readable_spaces, require_space
from .storage import ImageStore


class BodyLimit:
    def __init__(self, app, limit):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.limit:
                return await JSONResponse(
                    {"code": "INPUT_TOO_LARGE", "message": "请求字节超限"}, 413
                )(scope, receive, send)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)


def create_app(settings=None, sessions=None):
    settings = settings or Settings()
    engine, default_sessions = database(settings.database_url)
    sessions = sessions or default_sessions
    app = FastAPI(title="Lume", version="0.1.0")
    app.add_middleware(BodyLimit, limit=settings.max_request_bytes)
    app.state.settings, app.state.sessions = settings, sessions
    store = ImageStore(settings)

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse({"code": error.code, "message": error.message}, error.status)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, error):
        return JSONResponse({"code": "STORE_UNAVAILABLE", "message": "存储操作未完成"}, 503)

    def user(authorization: Annotated[str | None, Header()] = None):
        if not authorization or not authorization.startswith("Bearer "):
            raise DomainError("UNAUTHENTICATED", "请提供访问令牌", 401)
        with sessions() as session:
            return authenticate(session, authorization[7:])

    CurrentUser = Annotated[Principal, Depends(user)]

    def owned_task(session, task_id, user_id):
        task = session.get(Task, task_id)
        if not task or task.owner_id != user_id:
            raise DomainError("NOT_FOUND", "对象不可用", 404)
        return task

    def owned_answer(session, answer_id, user_id):
        answer = session.get(Answer, answer_id)
        if not answer:
            raise DomainError("NOT_FOUND", "对象不可用", 404)
        owned_task(session, answer.task_id, user_id)
        check_dependencies(session, user_id, answer.dependencies)
        return answer

    @app.get("/api/health")
    def health():
        with sessions() as session:
            session.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "provider": settings.provider,
            "provider_label": provider_for(settings).label,
            "qq_configured": bool(
                settings.qq_app_id and settings.qq_secret and len(settings.qq_webhook_token) >= 32
            ),
        }

    @app.get("/api/me")
    def me(actor: CurrentUser):
        return {"id": actor.id, "name": actor.name, "admin": actor.admin}

    @app.get("/api/spaces")
    def spaces(actor: CurrentUser):
        with sessions() as session:
            pairs = session.execute(
                select(Space, Grant)
                .join(Grant)
                .where(
                    Grant.user_id == actor.id, or_(Grant.read.is_(True), Grant.maintain.is_(True))
                )
                .order_by(Space.name)
            ).all()
            return [
                {
                    "id": s.id,
                    "name": s.name,
                    "read": g.read,
                    "maintain": g.maintain,
                    "qq_enabled": s.ingest_enabled,
                    "message_count": session.scalar(
                        select(func.count()).select_from(Message).where(Message.space_id == s.id)
                    ),
                }
                for s, g in pairs
            ]

    @app.post("/api/spaces", status_code=201)
    def create_space(body: SpaceInput, actor: CurrentUser):
        if not actor.admin:
            raise DomainError("FORBIDDEN", "需要管理资格", 403)
        with sessions.begin() as session:
            space = Space(**body.model_dump())
            session.add(space)
            session.flush()
            session.add(Grant(user_id=actor.id, space_id=space.id, read=True, maintain=True))
            return {"id": space.id, "name": space.name}

    @app.put("/api/spaces/{space_id}/grants/{user_id}")
    def grant(space_id: str, user_id: str, body: GrantInput, actor: CurrentUser):
        if not actor.admin:
            raise DomainError("FORBIDDEN", "需要管理资格", 403)
        with sessions.begin() as session:
            require_space(session, actor.id, space_id, maintain=True)
            if not session.get(Principal, user_id):
                raise DomainError("NOT_FOUND", "对象不可用", 404)
            session.merge(Grant(user_id=user_id, space_id=space_id, **body.model_dump()))
        return {"updated": True}

    @app.post("/api/spaces/{space_id}/imports", status_code=202)
    def imports(space_id: str, body: ImportInput, actor: CurrentUser):
        with sessions.begin() as session:
            require_space(session, actor.id, space_id, maintain=True)
            results = ingest(session, settings, store, space_id, body.messages)
        return {"state": "accepted", "messages": results}

    @app.get("/api/spaces/{space_id}/messages")
    def messages(space_id: str, actor: CurrentUser):
        with sessions() as session:
            require_space(session, actor.id, space_id)
            rows = session.scalars(
                select(Message)
                .where(Message.space_id == space_id, Message.active.is_(True))
                .order_by(Message.id)
                .limit(100)
            ).all()
            return [message_view(session, message) for message in rows]

    @app.post("/api/messages/{message_id}/deactivate")
    def deactivate(message_id: str, actor: CurrentUser):
        with sessions.begin() as session:
            message = session.get(Message, message_id, with_for_update=True)
            if not message:
                raise DomainError("NOT_FOUND", "对象不可用", 404)
            require_space(session, actor.id, message.space_id, maintain=True)
            message.active = False
        return {"active": False}

    @app.get("/api/spaces/{space_id}/jobs")
    def jobs(space_id: str, actor: CurrentUser):
        with sessions() as session:
            require_space(session, actor.id, space_id, maintain=True)
            rows = session.scalars(
                select(ProcessingJob).join(Message).where(Message.space_id == space_id).limit(100)
            ).all()
            return [
                {
                    "id": j.id,
                    "message_id": j.message_id,
                    "version": j.version,
                    "state": j.state,
                    "error": j.error,
                }
                for j in rows
            ]

    @app.post("/api/tasks", status_code=202)
    def create_task(body: TaskInput, actor: CurrentUser):
        with sessions.begin() as session:
            allowed = readable_spaces(session, actor.id, body.space_ids)
            if not allowed:
                raise DomainError("NO_READABLE_SCOPE", "没有可读取的资料范围", 403)
            for answer_id in body.history_ids:
                answer = owned_answer(session, answer_id, actor.id)
                for dependency in answer.dependencies:
                    if session.get(Message, dependency["message_id"]).space_id not in allowed:
                        raise DomainError("HISTORY_OUTSIDE_SCOPE", "历史超出本次范围")
            config = {
                k: getattr(settings, k)
                for k in (
                    "max_model_calls",
                    "max_tool_calls",
                    "max_image_calls",
                    "max_context_chars",
                    "max_recoveries",
                    "lease_seconds",
                    "retrieval_k",
                    "rrf_constant",
                )
            }
            config["rules_id"] = settings.rules_id
            config["require_image"] = body.require_image
            config["answer_contract"] = (
                "source-excerpts-v1" if settings.provider == "ollama" else "legacy"
            )
            task = Task(
                owner_id=actor.id,
                question=body.question,
                requested_scope=allowed,
                history_ids=body.history_ids,
                config=config,
                deadline=now() + timedelta(seconds=settings.task_timeout),
            )
            session.add(task)
            session.flush()
            return {"id": task.id, "state": task.state}

    @app.get("/api/tasks")
    def list_tasks(actor: CurrentUser):
        with sessions() as session:
            rows = session.scalars(
                select(Task)
                .where(Task.owner_id == actor.id)
                .order_by(Task.created_at.desc())
                .limit(50)
            ).all()
            return [
                {
                    "id": t.id,
                    "question": t.question,
                    "state": t.state,
                    "created_at": t.created_at.isoformat(),
                }
                for t in rows
            ]

    @app.get("/api/tasks/{task_id}")
    def task_status(task_id: str, actor: CurrentUser):
        with sessions() as session:
            task = owned_task(session, task_id, actor.id)
            answer = session.scalar(select(Answer.id).where(Answer.task_id == task.id))
            return {
                "id": task.id,
                "question": task.question,
                "state": task.state,
                "model_calls": task.model_calls,
                "tool_calls": task.tool_calls,
                "image_calls": task.image_calls,
                "error": task.error,
                "answer_id": answer,
            }

    @app.post("/api/tasks/{task_id}/cancel")
    def cancel(task_id: str, actor: CurrentUser):
        with sessions.begin() as session:
            task = owned_task(session, task_id, actor.id)
            task = session.get(Task, task.id, with_for_update=True, populate_existing=True)
            if task.state not in TERMINAL:
                task.state = "cancelled" if task.state == "queued" else "cancel_requested"
                session.add(TaskEvent(task_id=task.id, kind=task.state))
            return {"id": task.id, "state": task.state, "note": "业务取消不证明外部推理已停止计算"}

    @app.get("/api/tasks/{task_id}/events")
    def events(task_id: str, actor: CurrentUser, after: int = 0):
        with sessions() as session:
            owned_task(session, task_id, actor.id)
            rows = session.scalars(
                select(TaskEvent)
                .where(TaskEvent.task_id == task_id, TaskEvent.id > max(0, after))
                .order_by(TaskEvent.id)
                .limit(100)
            ).all()
            return [{"id": e.id, "kind": e.kind, "elapsed": e.elapsed} for e in rows]

    @app.get("/api/answers/{answer_id}")
    def answer_view(answer_id: str, actor: CurrentUser):
        with sessions() as session:
            answer = owned_answer(session, answer_id, actor.id)
            return {
                "id": answer.id,
                "text": answer.text,
                "citation_ids": answer.citation_ids,
                "dependencies": answer.dependencies,
            }

    @app.get("/api/observations/{observation_id}")
    def observation_view(observation_id: str, actor: CurrentUser):
        with sessions() as session:
            observation = session.get(Observation, observation_id)
            if not observation:
                raise DomainError("NOT_FOUND", "对象不可用", 404)
            owned_task(session, observation.task_id, actor.id)
            check_dependencies(session, actor.id, observation.dependencies)
            return {"id": observation.id, "kind": observation.kind, "content": observation.content}

    @app.get("/api/images/{image_id}")
    def image_view(image_id: str, actor: CurrentUser):
        with sessions() as session:
            image = session.get(ImageAsset, image_id)
            if not image:
                raise DomainError("NOT_FOUND", "对象不可用", 404)
            message = current_message(session, actor.id, image.message_id)
            if image.version != message.version or not image.blob:
                raise DomainError("NOT_FOUND", "图片不可用", 404)
            return FileResponse(
                store.path(image.blob), media_type=image.mime, headers={"Cache-Control": "no-store"}
            )

    @app.post("/integrations/qq/{webhook_token}")
    async def qq_webhook(webhook_token: str, request: Request):
        authorize_path(settings, webhook_token, request.headers.get("X-Bot-Appid", ""))
        raw = await request.body()
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise DomainError("QQ_PAYLOAD_INVALID", "回调格式无效", 422) from None
        if not isinstance(payload, dict):
            raise DomainError("QQ_PAYLOAD_INVALID", "回调格式无效", 422)
        if payload.get("op") == 13:
            data = payload.get("d", {})
            if not isinstance(data, dict) or not all(
                isinstance(data.get(k), str) and 0 < len(data[k]) <= 1000
                for k in ("plain_token", "event_ts")
            ):
                raise DomainError("QQ_PAYLOAD_INVALID", "验证字段无效", 422)
            # Challenges also require the secret callback path; no public signing oracle.
            signature = (
                key_for(settings.qq_secret)
                .sign((data["event_ts"] + data["plain_token"]).encode())
                .hex()
            )
            return {"plain_token": data["plain_token"], "signature": signature}
        verify_signature(
            settings.qq_secret,
            request.headers.get("X-Signature-Timestamp", ""),
            raw,
            request.headers.get("X-Signature-Ed25519", ""),
            settings.qq_timestamp_window,
        )
        with sessions.begin() as session:
            return handle_event(session, settings, store, payload)

    distribution = Path("frontend/dist")
    if distribution.is_dir():
        app.mount("/", StaticFiles(directory=distribution, html=True), name="workbench")
    return app


app = create_app()
