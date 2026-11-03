"""Run opt-in local Ollama smoke checks against synthetic data and an isolated PG schema.

No credentials, model thinking text, or existing messages are exported. This is a
connectivity/workflow check, not a retrieval benchmark or a semantic quality score.
"""

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import subprocess
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from lume.agent import Runner
from lume.api import create_app
from lume.config import Settings
from lume.demo import sample_messages
from lume.models import (
    ActionRecord,
    Artifact,
    Base,
    Grant,
    ImageAsset,
    Observation,
    ProcessingJob,
    RuntimeSetting,
    Space,
)
from lume.processing import Processor
from lume.providers import OllamaProvider
from lume.schemas import AgentAction
from lume.security import create_user
from lume.storage import ImageStore
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker


class RecordingProvider(OllamaProvider):
    """Retain final structured decisions only; do not export a model reasoning trace."""

    def __init__(self, settings):
        super().__init__(settings)
        self.decisions = []

    async def plan(self, question, observations, history, **requirements):
        action = await super().plan(question, observations, history, **requirements)
        self.decisions.append(action)
        return action


def save(path, report):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


async def timed(report, path, name, action):
    started = time.monotonic()
    row = {"stage": name, "started_at": datetime.now(UTC).isoformat()}
    report["stages"].append(row)
    save(path, report)
    try:
        row["result"] = await action()
        row["status"] = "returned"
    except Exception as error:
        # Exception strings may contain database URLs or payloads. Export types only.
        row.update(status="error", error=type(error).__name__)
        if isinstance(error, httpx.HTTPStatusError):
            row["http_status"] = error.response.status_code
    row["elapsed_seconds"] = round(time.monotonic() - started, 3)
    save(path, report)
    print(json.dumps({k: v for k, v in row.items() if k != "result"}), flush=True)
    return row


async def validate(args, path, report):
    async with httpx.AsyncClient(base_url=args.ollama_url, timeout=10, trust_env=False) as client:
        response = await client.get("/api/version")
        response.raise_for_status()
        report["ollama_version"] = response.json()["version"]
        response = await client.get("/api/tags")
        response.raise_for_status()
        selected = {"embeddinggemma:latest", "qwen3:4b", "qwen2.5vl:3b"}
        models = sorted(
            [m for m in response.json()["models"] if m["name"] in selected],
            key=lambda model: model["name"],
        )
        if {m["name"] for m in models} != selected:
            raise ValueError("Pull all three documented models first")
        report["models"] = [
            {key: model[key] for key in ("name", "digest", "size", "details")} for model in models
        ]
    revision = hashlib.sha256(json.dumps(report["models"], sort_keys=True).encode()).hexdigest()[
        :24
    ]
    with tempfile.TemporaryDirectory(prefix="lume-model-check-") as directory:
        settings = Settings(
            _env_file=None,
            provider="ollama",
            ollama_url=args.ollama_url,
            database_url=args.database_url,
            data_dir=Path(directory),
            embed_model="embeddinggemma",
            chat_model="qwen3:4b",
            vision_model="qwen2.5vl:3b",
            model_revision="digest-" + revision,
            task_timeout=args.task_timeout,
            ocr_lang="eng",
        )
        report["configuration"] = {
            key: getattr(settings, key)
            for key in (
                "provider",
                "rules_id",
                "task_timeout",
                "processing_timeout",
                "max_model_calls",
                "max_tool_calls",
                "max_image_calls",
                "max_context_chars",
                "retrieval_k",
                "rrf_constant",
                "lease_seconds",
            )
        }
        provider = RecordingProvider(settings)

        async def embedding():
            vector = await provider.embed("合成资料：v1.8连接池pool_size调整为20后复测恢复。")
            return {
                "dimension": len(vector),
                "norm": math.sqrt(sum(v * v for v in vector)),
                "vector": vector,
            }

        async def planning():
            raw = await provider.plan("E_CONN_42在v1.8环境如何处理？", [], [])
            return AgentAction.model_validate(raw).model_dump()

        store = ImageStore(settings)
        fixture = sample_messages()
        image = store.decode(fixture[-1].images[0].base64)
        image_data = store.path(image["blob"]).read_bytes()
        report["fixture"] = {
            "kind": "synthetic-only",
            "source_ids": [m.source_id for m in fixture],
            "texts": [m.text for m in fixture],
            "image_sha256": hashlib.sha256(image_data).hexdigest(),
            "image_expected_visible": {"pool_size": 20, "status": "healthy"},
        }

        async def vision():
            return await provider.vision("图中pool_size和status分别是什么？", image_data)

        await timed(report, path, "embedding", embedding)
        await timed(report, path, "structured_action", planning)
        await timed(report, path, "vision", vision)

        schema = "modelcheck_" + uuid.uuid4().hex
        admin = create_engine(args.database_url)
        engine = None
        created = False
        try:
            with admin.begin() as connection:
                report["postgres_version"] = connection.scalar(text("SELECT version()"))
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                report["pgvector_version"] = connection.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname='vector'")
                )
                connection.execute(text(f"CREATE SCHEMA {schema}"))
                created = True
            engine = create_engine(
                args.database_url,
                connect_args={"options": f"-csearch_path={schema},public"},
            )
            Base.metadata.create_all(engine, checkfirst=False)
            sessions = sessionmaker(engine, expire_on_commit=False)
            with sessions.begin() as session:
                user, token = create_user(session, "synthetic-model-check", admin=True)
                space = Space(name="真实模型联调 · 合成资料")
                session.add(space)
                session.flush()
                session.add_all(
                    [
                        Grant(user_id=user.id, space_id=space.id, read=True, maintain=True),
                        RuntimeSetting(key="rules_id", value=settings.rules_id),
                    ]
                )
            app = create_app(settings, sessions)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://synthetic-check",
                headers={"Authorization": "Bearer " + token},
            ) as client:
                response = await client.post(
                    f"/api/spaces/{space.id}/imports",
                    json={"messages": [m.model_dump(mode="json") for m in fixture]},
                )
                response.raise_for_status()
                processor = Processor(sessions, settings, provider, store)

                async def processing():
                    while await processor.run_once():
                        pass
                    with sessions() as session:
                        return {
                            "jobs": [
                                {"state": j.state, "error": j.error}
                                for j in session.scalars(select(ProcessingJob))
                            ],
                            "artifacts": [
                                {"message_id": a.message_id, "embedding_space": a.embedding_space}
                                for a in session.scalars(select(Artifact))
                            ],
                            "images": [
                                {
                                    "status": i.status,
                                    "error": i.error,
                                    "ocr_text": i.ocr_text,
                                    "description": i.description,
                                }
                                for i in session.scalars(select(ImageAsset))
                            ],
                        }

                await timed(report, path, "ingestion_processing", processing)
                runner = Runner(sessions, settings, provider, store)
                for name, question in [
                    ("text_task", "E_CONN_42在v1.8环境如何处理，复测结果是什么？"),
                    ("image_task", "请核查连接池参数示意图，图中的pool_size和status分别是什么？"),
                    ("unanswerable_task", "v9.9环境的GPU显存容量是多少GB？资料未记录时明确说明。"),
                ]:

                    async def ask(question=question, require_image=name == "image_task"):
                        provider.decisions.clear()
                        response = await client.post(
                            "/api/tasks",
                            json={
                                "question": question,
                                "space_ids": [space.id],
                                "require_image": require_image,
                            },
                        )
                        response.raise_for_status()
                        task_id = response.json()["id"]
                        await runner.run_once()
                        response = await client.get("/api/tasks/" + task_id)
                        response.raise_for_status()
                        result = response.json()
                        result["question"] = question
                        result["require_image"] = require_image
                        result["model_decisions"] = list(provider.decisions)
                        if result["answer_id"]:
                            answer = await client.get("/api/answers/" + result["answer_id"])
                            answer.raise_for_status()
                            result["answer"] = answer.json()
                        with sessions() as session:
                            result["actions"] = [
                                {"kind": a.kind, "state": a.state}
                                for a in session.scalars(
                                    select(ActionRecord)
                                    .where(ActionRecord.task_id == task_id)
                                    .order_by(ActionRecord.created_at, ActionRecord.id)
                                )
                            ]
                            result["observations"] = [
                                {
                                    "id": o.id,
                                    "kind": o.kind,
                                    "content": o.content,
                                    "dependencies": o.dependencies,
                                }
                                for o in session.scalars(
                                    select(Observation)
                                    .where(Observation.task_id == task_id)
                                    .order_by(Observation.created_at, Observation.id)
                                )
                            ]
                        return result

                    await timed(report, path, name, ask)
        finally:
            if engine is not None:
                engine.dispose()
            if created:
                with admin.begin() as connection:
                    connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            admin.dispose()
            report["isolated_schema_removed"] = created
            save(path, report)


def workflow_checks(report):
    stages = {s["stage"]: s for s in report["stages"]}

    def result(name):
        return stages.get(name, {}).get("result", {})

    text_result, image_result = result("text_task"), result("image_task")
    image_observations = {
        o["id"]
        for o in image_result.get("observations", [])
        if o["kind"] == "image_observation" and o["content"].get("semantic")
    }
    processing = result("ingestion_processing")
    return {
        "embedding_returned": stages.get("embedding", {}).get("status") == "returned",
        "first_action_search": result("structured_action").get("kind") == "search",
        "vision_returned": result("vision").get("semantic") is True,
        "four_artifacts_ready": len(processing.get("artifacts", [])) == 4
        and len(processing.get("jobs", [])) == 4
        and all(j["state"] == "ready" for j in processing.get("jobs", [])),
        "image_processed": len(processing.get("images", [])) == 1
        and processing["images"][0]["status"] == "ready",
        "text_answer_published": text_result.get("state") == "completed"
        and bool(text_result.get("answer", {}).get("citation_ids")),
        "image_answer_cites_image_observation": image_result.get("state") == "completed"
        and bool(
            image_observations.intersection(image_result.get("answer", {}).get("citation_ids", []))
        ),
        "unanswerable_marked_insufficient": result("unanswerable_task").get("state")
        == "insufficient",
        "schema_cleanup": report.get("isolated_schema_removed") is True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("LUME_TEST_DATABASE_URL"))
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11435")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task-timeout", type=int, default=90)
    args = parser.parse_args()
    endpoint = urlparse(args.ollama_url)
    if endpoint.scheme != "http" or endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("This synthetic verification command only calls a local Ollama service")
    if not args.database_url or args.task_timeout <= 0:
        parser.error("Set LUME_TEST_DATABASE_URL and a positive task timeout")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite a first failed run with a later successful one.
    with args.output.open("x"):
        pass
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "source_commit": revision,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_dirty": bool(
            subprocess.run(
                ["git", "status", "--porcelain"], check=True, capture_output=True, text=True
            ).stdout.strip()
        ),
        "scope": "synthetic smoke; no quality benchmark, load test, or QQ live integration",
        "stages": [],
    }
    try:
        asyncio.run(validate(args, args.output, report))
    except Exception as error:
        report["fatal_error"] = type(error).__name__
    report["finished_at"] = datetime.now(UTC).isoformat()
    report["workflow_checks"] = workflow_checks(report)
    report["semantic_review"] = "pending manual comparison against the synthetic fixture"
    save(args.output, report)
    if (
        "fatal_error" in report
        or any(s["status"] == "error" for s in report["stages"])
        or not all(report["workflow_checks"].values())
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
