import asyncio
import json
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import and_, or_, select

from .knowledge import current_message, read_context, search
from .leases import maintain_lease
from .models import (
    ActionRecord,
    Answer,
    ImageAsset,
    Message,
    Observation,
    RuntimeSetting,
    Task,
    TaskEvent,
    now,
)
from .schemas import AgentAction
from .security import DomainError, check_dependencies, dependency_union

TERMINAL = {"completed", "insufficient", "limited", "failed", "cancelled"}


class StaleRun(Exception):
    pass


class BudgetEnded(Exception):
    pass


class Runner:
    def __init__(self, sessions, settings, provider, store):
        self.sessions, self.settings, self.provider, self.store = (
            sessions,
            settings,
            provider,
            store,
        )

    def guard(self, task, epoch):
        if (
            task.state != "running"
            or task.epoch != epoch
            or not task.lease_until
            or task.lease_until <= now()
        ):
            raise StaleRun
        if task.deadline <= now():
            raise BudgetEnded

    def reserve(self, task_id, epoch, kind):
        with self.sessions.begin() as session:
            task = session.get(Task, task_id, with_for_update=True)
            self.guard(task, epoch)
            check_dependencies(session, task.owner_id, [])
            if kind in {"model", "vision", "embedding"}:
                if task.model_calls >= task.config["max_model_calls"]:
                    raise BudgetEnded
                task.model_calls += 1
            else:
                if task.tool_calls >= task.config["max_tool_calls"]:
                    raise BudgetEnded
                task.tool_calls += 1
            if kind == "vision":
                if task.image_calls >= task.config["max_image_calls"]:
                    raise BudgetEnded
                task.image_calls += 1
            action = ActionRecord(task_id=task.id, epoch=epoch, kind=kind)
            session.add(action)
            session.add(TaskEvent(task_id=task.id, kind=f"reserved:{kind}"))
            session.flush()
            return action.id

    def mark_action(self, action_id):
        with self.sessions.begin() as session:
            action = session.get(ActionRecord, action_id, with_for_update=True)
            task = session.get(Task, action.task_id)
            action.state = (
                "returned"
                if task.epoch == action.epoch
                and task.state == "running"
                and task.lease_until > now()
                else "discarded"
            )

    def claim(self):
        with self.sessions.begin() as session:
            cancelled = session.scalar(
                select(Task)
                .where(Task.state == "cancel_requested")
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if cancelled:
                cancelled.state, cancelled.epoch = "cancelled", cancelled.epoch + 1
                session.add(TaskEvent(task_id=cancelled.id, kind="cancelled"))
                return cancelled.id, None
            task = session.scalar(
                select(Task)
                .where(
                    or_(
                        Task.state == "queued",
                        and_(Task.state == "running", Task.lease_until <= now()),
                    )
                )
                .order_by(Task.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not task:
                return None
            if task.deadline <= now():
                task.state = "limited"
                return task.id, None
            if task.state == "running":
                task.recoveries += 1
            if task.recoveries > task.config["max_recoveries"]:
                task.state, task.error = "failed", "RECOVERY_EXHAUSTED"
                return task.id, None
            task.epoch += 1
            task.state = "running"
            task.lease_until = now() + timedelta(
                seconds=task.config.get("lease_seconds", self.settings.lease_seconds)
            )
            session.add(TaskEvent(task_id=task.id, kind="running"))
            return task.id, task.epoch

    def renew(self, task_id, epoch):
        with self.sessions.begin() as session:
            task = session.get(Task, task_id, with_for_update=True)
            self.guard(task, epoch)
            check_dependencies(session, task.owner_id, [])
            task.lease_until = now() + timedelta(
                seconds=task.config.get("lease_seconds", self.settings.lease_seconds)
            )

    def finish(self, task_id, epoch, state, error=None):
        with self.sessions.begin() as session:
            task = session.get(Task, task_id, with_for_update=True)
            if task.epoch != epoch or task.state in TERMINAL or task.lease_until <= now():
                return
            if task.state == "cancel_requested":
                task.state = "cancelled"
            else:
                task.state, task.error = state, error
            session.add(
                TaskEvent(
                    task_id=task.id,
                    kind=task.state,
                    elapsed=(now() - task.created_at).total_seconds(),
                )
            )

    async def run_once(self):
        claimed = self.claim()
        if not claimed:
            return False
        task_id, epoch = claimed
        if epoch is None:
            return True
        try:
            with self.sessions() as session:
                task = session.get(Task, task_id)
                remaining = (task.deadline - now()).total_seconds()
            async with asyncio.timeout(max(0.001, remaining)):
                await maintain_lease(
                    self.execute(task_id, epoch),
                    min(2, task.config.get("lease_seconds", self.settings.lease_seconds) / 3),
                    lambda: self.renew(task_id, epoch),
                )
        except StaleRun:
            self.finish(task_id, epoch, "cancelled")
        except (BudgetEnded, TimeoutError):
            self.finish(task_id, epoch, "limited")
        except Exception as error:
            code = error.code if isinstance(error, DomainError) else type(error).__name__
            self.finish(task_id, epoch, "failed", code[:80])
        return True

    def inputs(self, task_id, epoch):
        with self.sessions() as session:
            task = session.get(Task, task_id)
            self.guard(task, epoch)
            rule = session.get(RuntimeSetting, "rules_id")
            if (
                task.config["rules_id"] != self.settings.rules_id
                or not rule
                or rule.value != task.config["rules_id"]
            ):
                raise DomainError("CONFIG_CHANGED", "运行配置已变化")
            rows = session.scalars(
                select(Observation)
                .where(Observation.task_id == task_id)
                .order_by(Observation.created_at, Observation.id)
            ).all()
            observations = [{"id": o.id, "kind": o.kind, "content": o.content} for o in rows]
            dependencies = dependency_union(*(o.dependencies for o in rows))
            history = []
            for answer_id in task.history_ids:
                answer = session.get(Answer, answer_id)
                owner = session.get(Task, answer.task_id) if answer else None
                if not owner or owner.owner_id != task.owner_id:
                    raise DomainError("HISTORY_UNAVAILABLE", "历史不可用")
                history.append({"question": owner.question, "answer": answer.text})
                dependencies = dependency_union(dependencies, answer.dependencies)
            check_dependencies(session, task.owner_id, dependencies)
            for d in dependencies:
                if session.get(Message, d["message_id"]).space_id not in task.requested_scope:
                    raise DomainError("HISTORY_OUTSIDE_SCOPE", "历史超出本次范围")
            if (
                len(json.dumps([task.question, observations, history], ensure_ascii=False))
                > task.config["max_context_chars"]
            ):
                raise BudgetEnded
            return task, observations, history, dependencies

    def save_observation(self, task_id, epoch, kind, content, dependencies):
        with self.sessions.begin() as session:
            task = session.get(Task, task_id, with_for_update=True)
            self.guard(task, epoch)
            check_dependencies(session, task.owner_id, dependencies)
            session.add(
                Observation(task_id=task_id, kind=kind, content=content, dependencies=dependencies)
            )
            session.add(TaskEvent(task_id=task_id, kind=f"observed:{kind}"))

    def publish(self, task_id, epoch, action, dependencies):
        with self.sessions.begin() as session:
            task = session.get(Task, task_id, with_for_update=True)
            self.guard(task, epoch)
            check_dependencies(session, task.owner_id, dependencies)
            for citation_id in action.citation_ids:
                observation = session.get(Observation, citation_id)
                if (
                    not observation
                    or observation.task_id != task_id
                    or observation.kind not in {"message_context", "image_observation"}
                ):
                    raise DomainError("INVALID_CITATION", "引用不属于已读取证据")
            if not action.insufficient and not action.citation_ids:
                raise DomainError("INVALID_CITATION", "正常答案需要实际证据引用")
            session.add(
                Answer(
                    task_id=task_id,
                    text=action.answer,
                    citation_ids=action.citation_ids,
                    dependencies=dependencies,
                )
            )
            task.state = "insufficient" if action.insufficient else "completed"
            session.add(TaskEvent(task_id=task_id, kind=task.state))

    async def execute(self, task_id, epoch):
        while True:
            task, observations, history, dependencies = self.inputs(task_id, epoch)
            model_attempt = self.reserve(task_id, epoch, "model")
            self.inputs(task_id, epoch)  # Recheck immediately before external input transmission.
            raw = await self.provider.plan(task.question, observations, history)
            self.mark_action(model_attempt)
            try:
                action = AgentAction.model_validate(raw)
            except ValidationError:
                with self.sessions.begin() as session:
                    session.add(TaskEvent(task_id=task_id, kind="action_rejected"))
                continue  # The already spent model-call allowance is never refunded.
            task, observations, history, dependencies = self.inputs(task_id, epoch)
            if action.kind == "final":
                self.publish(task_id, epoch, action, dependencies)
                return
            tool_action = self.reserve(task_id, epoch, action.kind)
            if action.kind == "search":
                embedding_attempt = self.reserve(task_id, epoch, "embedding")
                content, deps = await search(
                    self.sessions,
                    self.settings.model_copy(
                        update={
                            "retrieval_k": task.config["retrieval_k"],
                            "rrf_constant": task.config["rrf_constant"],
                        }
                    ),
                    self.provider,
                    task.owner_id,
                    action.query,
                    task.requested_scope,
                )
                self.mark_action(embedding_attempt)
                kind = "candidate_only"
            elif action.kind == "read_context":
                candidate_ids = {
                    c["message_id"]
                    for o in observations
                    if o["kind"] == "candidate_only"
                    for c in o["content"]["candidates"]
                }
                if action.target_id not in candidate_ids:
                    raise DomainError("INVALID_TARGET", "只允许读取当前候选")
                with self.sessions() as session:
                    content, deps = read_context(
                        session, task.owner_id, action.target_id, task.requested_scope
                    )
                kind = "message_context"
            else:
                image_ids = {
                    i["id"]
                    for o in observations
                    if o["kind"] == "message_context"
                    for m in o["content"]["messages"]
                    for i in m["images"]
                }
                if action.target_id not in image_ids:
                    raise DomainError("INVALID_TARGET", "图片不属于已读上下文")
                with self.sessions() as session:
                    image = session.get(ImageAsset, action.target_id)
                    message = current_message(
                        session, task.owner_id, image.message_id, task.requested_scope
                    )
                    if image.version != message.version or not image.blob:
                        raise DomainError("IMAGE_UNAVAILABLE", "原图不可用")
                    image_data = self.store.path(image.blob).read_bytes()
                    deps = [{"message_id": message.id, "version": message.version}]
                vision_attempt = self.reserve(task_id, epoch, "vision")
                self.inputs(task_id, epoch)
                content = await self.provider.vision(task.question, image_data)
                self.mark_action(vision_attempt)
                content.update(image_id=action.target_id)
                kind = "image_observation"
            self.mark_action(tool_action)
            self.save_observation(task_id, epoch, kind, content, deps)
