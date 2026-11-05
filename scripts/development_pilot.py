"""Run only development queries through the real API/DB/models; audit separately offline."""

import argparse
import asyncio
import base64
import copy
import hashlib
import json
import os
import platform
import subprocess
import tempfile
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from lume.agent import TERMINAL, Runner
from lume.api import create_app
from lume.config import Settings
from lume.models import (
    ActionRecord,
    Artifact,
    Base,
    ImageAsset,
    Message,
    Observation,
    ProcessingJob,
    RuntimeSetting,
    Task,
    TaskEvent,
)
from lume.processing import Processor
from lume.security import create_user
from lume.storage import ImageStore
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from scripts.evaluation_dataset import digest, local_path, read_rows, require, task_payload
from scripts.validate_real_models import RecordingProvider, save

BASELINE = "5ca664f4c97198916856fc875e4a586a778df19a"
DATASET_SHA = "410134ca19cd3e8e14bbb411771698612d7bd1b3cf9ebdb666d83c604b6d60c2"
MODEL_NAMES = {"embeddinggemma:latest", "qwen3:4b", "qwen2.5vl:3b"}


def load_run_inputs(root):
    require(digest(root / "manifest.json") == DATASET_SHA, "dataset snapshot changed")
    manifest = json.loads((root / "manifest.json").read_text())
    for path, expected in manifest["files"].items():
        require(digest(local_path(root, path)) == expected, "dataset file digest mismatch")
    # Hashing verifies the bundle. No reference labels or heldout questions are parsed here.
    scenarios = [
        s
        for s in json.loads((root / "scenarios.json").read_text())["scenarios"]
        if s["split"] == "dev"
    ]
    queries = read_rows(root / "queries-dev.jsonl")
    require(len(scenarios) == 4 and len(queries) == 16, "development input counts mismatch")
    ids = {s["id"] for s in scenarios}
    require(all(set(q["scope_scenarios"]) <= ids for q in queries), "non-development scope")
    for query in queries:
        task_payload(query, {sid: "scope-" + sid for sid in ids})
    return scenarios, queries


def import_packets(root, scenario):
    assets = {a["id"]: a for a in scenario["assets"]}
    packets = []
    for message in scenario["messages"]:
        packet = {**message, "images": []}
        for image in message["images"]:
            asset = assets[image["asset_id"]]
            data = local_path(root, asset["path"]).read_bytes()
            require(hashlib.sha256(data).hexdigest() == asset["sha256"], "asset changed")
            packet["images"].append(
                {"filename": asset["filename"], "base64": base64.b64encode(data).decode()}
            )
        packets.append(packet)
    return packets


def public_request(payload):
    result = copy.deepcopy(payload)
    for message in result.get("messages", []):
        if "images" in message:
            message["images"] = [
                {
                    "sha256": hashlib.sha256(base64.b64decode(encoded)).hexdigest(),
                    "byte_count": len(base64.b64decode(encoded)),
                }
                for encoded in message["images"]
            ]
    return result


class PilotProvider(RecordingProvider):
    def __init__(self, settings, report, output):
        super().__init__(settings)
        self.report, self.output, self.calls = report, output, []
        self.phase, self.query_id = "processing", None
        self.purpose = None

    async def assess_support(self, question, sources, **requirements):
        self.purpose = "support_review"
        try:
            return await super().assess_support(question, sources, **requirements)
        finally:
            self.purpose = None

    async def _post(self, endpoint, payload):
        purpose = self.purpose or (
            "embedding"
            if endpoint == "/api/embed"
            else "vision"
            if any(m.get("images") for m in payload.get("messages", []))
            else "planning"
        )
        row = {
            "purpose": purpose,
            "phase": self.phase,
            "query_id": self.query_id,
            "endpoint": endpoint,
            "request": public_request(payload),
            "started_at": datetime.now(UTC).isoformat(),
        }
        self.calls.append(row)
        self.report["calls"].append(row)
        started = time.monotonic()
        try:
            data = await super()._post(endpoint, payload)
            row.update(
                status="returned",
                usage={
                    k: data[k]
                    for k in [
                        "model",
                        "done_reason",
                        "prompt_eval_count",
                        "eval_count",
                        "total_duration",
                        "load_duration",
                        "prompt_eval_duration",
                        "eval_duration",
                    ]
                    if k in data
                },
            )
            if "message" in data:
                row["response_content"] = data["message"].get("content")
            if "embeddings" in data:
                row["embedding_dimensions"] = [len(v) for v in data["embeddings"]]
                row["embedding_sha256"] = hashlib.sha256(
                    json.dumps(data["embeddings"]).encode()
                ).hexdigest()
            # Keep final content even if parsing later fails, never message.thinking.
            return data
        except BaseException as error:
            row.update(
                status="cancelled" if isinstance(error, asyncio.CancelledError) else "error",
                error_type=type(error).__name__,
            )
            if isinstance(error, httpx.HTTPStatusError):
                row["http_status"] = error.response.status_code
            raise
        finally:
            row["elapsed_seconds"] = round(time.monotonic() - started, 3)
            save(self.output, self.report)


async def model_metadata(url, frozen_manifest):
    expected = {m["name"]: m["digest"] for m in json.loads(frozen_manifest.read_text())["models"]}
    async with httpx.AsyncClient(base_url=url, timeout=10, trust_env=False) as client:
        version = await client.get("/api/version")
        version.raise_for_status()
        response = await client.get("/api/tags")
        response.raise_for_status()
        models = sorted(
            [m for m in response.json()["models"] if m["name"] in MODEL_NAMES],
            key=lambda m: m["name"],
        )
    observed = {m["name"]: m["digest"] for m in models}
    require(set(observed) == MODEL_NAMES and observed == expected, "frozen model weights mismatch")
    return version.json()["version"], [
        {k: m[k] for k in ["name", "digest", "size", "details"]} for m in models
    ]


async def execute(args, report):
    scenarios, queries = load_run_inputs(args.dataset)
    version, models = await model_metadata(args.ollama_url, args.model_manifest)
    report.update(ollama_version=version, models=models)
    identities = {m["name"]: m["digest"] for m in models}
    model_revision = (
        "weights-"
        + hashlib.sha256(json.dumps(identities, sort_keys=True).encode()).hexdigest()[:24]
    )
    with tempfile.TemporaryDirectory(prefix="lume-dev-pilot-") as directory:
        settings = Settings(
            _env_file=None,
            provider="ollama",
            database_url=args.database_url,
            data_dir=Path(directory),
            ollama_url=args.ollama_url,
            embed_model="embeddinggemma",
            chat_model="qwen3:4b",
            vision_model="qwen2.5vl:3b",
            model_revision=model_revision,
            ocr_lang="eng",
            task_timeout=90,
            processing_timeout=90,
            lease_seconds=15,
            max_model_calls=12,
            max_tool_calls=8,
            max_image_calls=2,
            max_context_chars=32000,
            max_recoveries=2,
            retrieval_k=12,
            rrf_constant=60,
        )
        report["configuration"] = {
            k: getattr(settings, k)
            for k in [
                "provider",
                "rules_id",
                "task_timeout",
                "processing_timeout",
                "lease_seconds",
                "max_model_calls",
                "max_tool_calls",
                "max_image_calls",
                "max_context_chars",
                "max_recoveries",
                "retrieval_k",
                "rrf_constant",
            ]
        }
        provider, store = PilotProvider(settings, report, args.output), ImageStore(settings)
        schema, created, engine = "devpilot_" + uuid.uuid4().hex, False, None
        admin = create_engine(args.database_url)
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
                args.database_url, connect_args={"options": f"-csearch_path={schema},public"}
            )
            Base.metadata.create_all(engine, checkfirst=False)
            sessions = sessionmaker(engine, expire_on_commit=False)
            with sessions.begin() as session:
                user, token = create_user(session, "synthetic-development-pilot", admin=True)
                session.add(RuntimeSetting(key="rules_id", value=settings.rules_id))
            app = create_app(settings, sessions)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://development-pilot",
                headers={"Authorization": "Bearer " + token},
            ) as client:
                spaces = {}
                for scenario in scenarios:
                    response = await client.post(
                        "/api/spaces", json={"name": scenario["title"] + " · 合成开发资料"}
                    )
                    response.raise_for_status()
                    spaces[scenario["id"]] = response.json()["id"]
                    response = await client.post(
                        f"/api/spaces/{spaces[scenario['id']]}/imports",
                        json={"messages": import_packets(args.dataset, scenario)},
                    )
                    response.raise_for_status()
                report["imported_scenarios"] = list(spaces)
                processor = Processor(sessions, settings, provider, store)
                while await processor.run_once():
                    with sessions() as session:
                        report["processing"] = [
                            {"message_id": j.message_id, "state": j.state, "error": j.error}
                            for j in session.scalars(select(ProcessingJob))
                        ]
                    save(args.output, report)
                with sessions() as session:
                    messages = list(session.scalars(select(Message)))
                    source_map = {m.id: m.source_id for m in messages}
                    asset_map = {a["message_source_id"]: a for s in scenarios for a in s["assets"]}
                    report["sources"] = [
                        {
                            "message_id": m.id,
                            "source_id": m.source_id,
                            "version": m.version,
                            "space_id": m.space_id,
                        }
                        for m in messages
                    ]
                    report["images"] = [
                        {
                            "id": i.id,
                            "source_id": source_map[i.message_id],
                            "asset_id": asset_map[source_map[i.message_id]]["id"],
                            "digest": i.digest,
                            "status": i.status,
                            "error": i.error,
                            "ocr_text": i.ocr_text,
                            "description": i.description,
                        }
                        for i in session.scalars(select(ImageAsset))
                    ]
                    report["artifact_count"] = len(session.scalars(select(Artifact)).all())
                require(
                    len(report["sources"]) == 24
                    and report["artifact_count"] == 24
                    and len(report["processing"]) == 24
                    and all(j["state"] == "ready" for j in report["processing"]),
                    "incomplete development index; query stage not started",
                )
                print(
                    json.dumps({"processing_ready": 24, "images": len(report["images"])}),
                    flush=True,
                )
                runner = Runner(sessions, settings, provider, store)
                for query in queries:
                    provider.phase, provider.query_id = "task", query["id"]
                    provider.decisions.clear()
                    row = {
                        "query_id": query["id"],
                        "question": query["question"],
                        "scope_scenarios": query["scope_scenarios"],
                        "require_image": query["require_image"],
                        "started_at": datetime.now(UTC).isoformat(),
                    }
                    report["tasks"].append(row)
                    started = time.monotonic()
                    try:
                        response = await client.post("/api/tasks", json=task_payload(query, spaces))
                        response.raise_for_status()
                        task_id = response.json()["id"]
                        row["task_id"] = task_id
                        await runner.run_once()
                        response = await client.get("/api/tasks/" + task_id)
                        response.raise_for_status()
                        row["status"] = response.json()
                        row["model_decisions"] = list(provider.decisions)
                        with sessions() as session:
                            frozen_task = session.get(Task, task_id)
                            row["task_configuration"] = frozen_task.config
                            row["requested_scope"] = frozen_task.requested_scope
                            row["observations"] = [
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
                            row["actions"] = [
                                {"kind": a.kind, "state": a.state, "epoch": a.epoch}
                                for a in session.scalars(
                                    select(ActionRecord)
                                    .where(ActionRecord.task_id == task_id)
                                    .order_by(ActionRecord.created_at, ActionRecord.id)
                                )
                            ]
                            row["events"] = [
                                {"id": e.id, "kind": e.kind, "elapsed": e.elapsed}
                                for e in session.scalars(
                                    select(TaskEvent)
                                    .where(TaskEvent.task_id == task_id)
                                    .order_by(TaskEvent.id)
                                )
                            ]
                        if row["status"]["answer_id"]:
                            response = await client.get(
                                "/api/answers/" + row["status"]["answer_id"]
                            )
                            row["answer_read_http_status"] = response.status_code
                            response.raise_for_status()
                            row["answer"] = response.json()
                        require(row["status"]["state"] in TERMINAL, "task remained nonterminal")
                    except Exception as error:
                        row["harness_error"] = type(error).__name__
                        if isinstance(error, httpx.HTTPStatusError):
                            row["http_status"] = error.response.status_code
                    row["elapsed_seconds"] = round(time.monotonic() - started, 3)
                    save(args.output, report)
                    print(
                        json.dumps(
                            {
                                "query_id": query["id"],
                                "state": row.get("status", {}).get("state"),
                                "error": row.get("status", {}).get("error")
                                or row.get("harness_error"),
                                "elapsed_seconds": row["elapsed_seconds"],
                            }
                        ),
                        flush=True,
                    )
                    require(
                        not row.get("status") or row["status"]["state"] in TERMINAL,
                        "cannot safely schedule next query after nonterminal execution",
                    )
        finally:
            if engine is not None:
                engine.dispose()
            if created:
                with admin.begin() as connection:
                    connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            admin.dispose()
            report["isolated_schema_removed"] = created
            save(args.output, report)


def audit_report(run, dataset):
    require(
        run["dataset_manifest_sha256"] == digest(dataset / "manifest.json"), "audit dataset changed"
    )
    queries = {q["id"]: q for q in read_rows(dataset / "queries-dev.jsonl")}
    refs = {
        r["query_id"]: r for r in read_rows(dataset / "references.jsonl") if r["split"] == "dev"
    }
    require(
        all(t["query_id"] in queries for t in run["tasks"]), "audit contains non-development tasks"
    )
    require(
        len({t["query_id"] for t in run["tasks"]}) == len(run["tasks"]),
        "duplicate query executions must be kept in separate runs",
    )
    source_ids = {s["message_id"]: s["source_id"] for s in run.get("sources", [])}
    asset_ids = {i["id"]: i["asset_id"] for i in run.get("images", [])}
    rows = []
    for task in run["tasks"]:
        reference = refs[task["query_id"]]
        require(
            task["question"] == queries[task["query_id"]]["question"],
            "audit question differs from frozen query",
        )
        read, observed_images, cited = set(), set(), set()
        observations = {o["id"]: o for o in task.get("observations", [])}

        def ids_for(observation):
            if observation["kind"] == "message_context":
                return {source_ids[m["message_id"]] for m in observation["content"]["messages"]}
            if observation["kind"] == "image_observation" and observation["content"].get(
                "semantic"
            ):
                return {asset_ids[observation["content"]["image_id"]]}
            return set()

        for observation in observations.values():
            ids = ids_for(observation)
            if observation["kind"] == "image_observation":
                observed_images.update(ids)
            else:
                read.update(ids)
        for cid in task.get("answer", {}).get("citation_ids", []):
            require(cid in observations, "answer citation outside task observations")
            cited.update(ids_for(observations[cid]))
        selected = None
        if task.get("task_configuration", {}).get("answer_contract") in {
            "source-excerpts-v1",
            "reviewed-excerpts-v1",
        }:
            selected = set()
            decisions = task.get("model_decisions", [])
            if task.get("status", {}).get("state") == "completed" and decisions:
                for selection in decisions[-1].get("evidence", []):
                    observation = observations[selection["observation_id"]]
                    require(
                        observation["id"] in task["answer"]["citation_ids"],
                        "selected evidence was not published",
                    )
                    if selection.get("message_id"):
                        require(
                            selection["message_id"]
                            in {
                                m["message_id"] for m in observation["content"].get("messages", [])
                            },
                            "selected message is not in cited context",
                        )
                        selected.add(source_ids[selection["message_id"]])
                    else:
                        selected.update(ids_for(observation))
        proposed = set()
        support_reviews = [
            o["content"] for o in observations.values() if o["kind"] == "support_review"
        ]
        for review in support_reviews:
            for selection in review.get("selections", []):
                observation = observations[selection["observation_id"]]
                if selection.get("message_id"):
                    proposed.add(source_ids[selection["message_id"]])
                else:
                    proposed.update(ids_for(observation))
        groups = reference["minimal_evidence_sets"]
        rows.append(
            {
                "query_id": task["query_id"],
                "question": task["question"],
                "category": reference["category"],
                "state": task.get("status", {}).get("state"),
                "draft_expected_state": reference["expected_state"],
                "read_message_ids": sorted(read),
                "observed_image_ids": sorted(observed_images),
                "cited_evidence_ids": sorted(cited),
                "selected_evidence_ids": sorted(selected) if selected is not None else None,
                "draft_set_selected": any(set(g) <= selected for g in groups)
                if groups and selected is not None
                else None,
                "support_reviews": support_reviews,
                "proposed_evidence_ids": sorted(proposed),
                "draft_minimal_sets": groups,
                "draft_set_observed": any(set(g) <= read | observed_images for g in groups)
                if groups
                else None,
                "draft_set_cited": any(set(g) <= cited for g in groups) if groups else None,
                "answer": task.get("answer", {}).get("text"),
                "human_semantic_review": "pending",
            }
        )
    return {
        "scope": "offline development diagnostics against draft labels; no semantic quality scores",
        "run_source_commit": run["source_commit"],
        "state_counts": dict(Counter(r["state"] for r in rows)),
        "rows": rows,
        "human_reviewed_queries": 0,
        "quality_scores_computed": False,
    }


def write_audit_markdown(audit, path):
    lines = [
        "# 开发集真实试跑逐题审阅",
        "",
        "仅为开发诊断；参考标签人审0题。任务完成不等于回答正确，ID集合覆盖不等于逐断言支持。",
        "",
        "实际任务状态：" + json.dumps(audit["state_counts"], ensure_ascii=False),
        "",
    ]
    for row in audit["rows"]:
        lines.extend(
            [
                f"## {row['query_id']} / {row['category']}",
                "",
                row["question"],
                "",
                f"实际状态：{row['state']}；草稿预期：{row['draft_expected_state']}。",
                "",
                row["answer"] or "本题无已发布答案。",
                "",
                "已读消息：" + json.dumps(row["read_message_ids"], ensure_ascii=False),
                "原图观察：" + json.dumps(row["observed_image_ids"], ensure_ascii=False),
                "引用容器所含证据：" + json.dumps(row["cited_evidence_ids"], ensure_ascii=False),
                "实际选择展示：" + json.dumps(row["selected_evidence_ids"], ensure_ascii=False),
                "送入核查的提议来源："
                + json.dumps(row["proposed_evidence_ids"], ensure_ascii=False),
                "",
                "草稿最小集合：" + json.dumps(row["draft_minimal_sets"], ensure_ascii=False),
                f"草稿集合已观察：{row['draft_set_observed']}；已引用：{row['draft_set_cited']}。",
                "",
                f"草稿集合已选中展示：{row['draft_set_selected']}。",
                "发布前核查："
                + json.dumps(
                    [
                        {
                            k: review.get(k)
                            for k in [
                                "valid",
                                "accepted",
                                "issues",
                                "scope_constraints",
                                "assessment",
                            ]
                        }
                        for review in row["support_reviews"]
                    ],
                    ensure_ascii=False,
                ),
                "人工语义复核：待完成。",
                "",
            ]
        )
    path.write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    runner = commands.add_parser("run")
    runner.add_argument("--database-url", default=os.environ.get("LUME_TEST_DATABASE_URL"))
    runner.add_argument("--ollama-url", default="http://127.0.0.1:11435")
    runner.add_argument("--dataset", type=Path, default=Path("evaluation/dataset-v1"))
    runner.add_argument(
        "--model-manifest", type=Path, default=Path("docs/evidence/real-model/model-manifest.json")
    )
    runner.add_argument("--output", type=Path, required=True)
    runner.add_argument("--application-baseline", default=BASELINE)
    auditor = commands.add_parser("audit")
    auditor.add_argument("--run", type=Path, required=True)
    auditor.add_argument("--dataset", type=Path, default=Path("evaluation/dataset-v1"))
    auditor.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "audit":
        result = audit_report(json.loads(args.run.read_text()), args.dataset)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x"):
            pass
        save(args.output, result)
        write_audit_markdown(result, args.output.with_suffix(".md"))
        print(json.dumps(result["state_counts"], ensure_ascii=False))
        return
    endpoint = urlparse(args.ollama_url)
    require(
        endpoint.scheme == "http" and endpoint.hostname in {"localhost", "127.0.0.1", "::1"},
        "local Ollama required",
    )
    require(args.database_url, "LUME_TEST_DATABASE_URL required")
    require(
        not subprocess.check_output(
            ["git", "diff", args.application_baseline, "--", "backend/src/lume"], text=True
        ),
        "application behavior differs from frozen pilot baseline",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x"):
        pass
    report = {
        "date": datetime.now(UTC).date().isoformat(),
        "started_at": datetime.now(UTC).isoformat(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "source_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        ),
        "script_sha256": digest(Path(__file__)),
        "application_baseline": args.application_baseline,
        "dataset_manifest_sha256": digest(args.dataset / "manifest.json"),
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "scope": "16 development queries only; synthetic data, no formal quality evaluation",
        "offline_labels_parsed_during_run": False,
        "heldout_queries_executed": 0,
        "calls": [],
        "tasks": [],
    }
    try:
        asyncio.run(execute(args, report))
    except Exception as error:
        report["fatal_error"] = type(error).__name__
    report["finished_at"] = datetime.now(UTC).isoformat()
    report["state_counts"] = dict(
        Counter(t.get("status", {}).get("state", "harness_error") for t in report["tasks"])
    )
    save(args.output, report)
    if (
        report.get("fatal_error")
        or len(report["tasks"]) != 16
        or any(t.get("harness_error") for t in report["tasks"])
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
