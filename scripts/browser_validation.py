"""Opt-in real HTTP/API/worker/browser checks with new synthetic data and isolated SQL.

This is a workflow check, not a retrieval benchmark, pixel-accuracy score or QQ test.
Child configuration, access tokens and raw service logs stay in a temporary directory.
"""

import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
import uvicorn
from lume.agent import Runner
from lume.api import create_app
from lume.config import Settings
from lume.models import (
    ActionRecord,
    Answer,
    Base,
    Observation,
    RuntimeSetting,
    Task,
)
from lume.processing import Processor
from lume.security import create_user
from lume.storage import ImageStore
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from scripts.development_pilot import PilotProvider, model_metadata
from scripts.read_load_validation import measure_reads, save

PROJECT = Path(__file__).resolve().parents[1]
MODEL_KINDS = {"model", "embedding", "vision", "support_review"}


def require(condition, description):
    if not condition:
        raise ValueError(description)


def sanitize(value, replacements):
    """Redact exact temporary secrets/paths before a browser report leaves runtime storage."""
    if isinstance(value, str):
        for original, replacement in replacements:
            value = value.replace(original, replacement)
        return value
    if isinstance(value, list):
        return [sanitize(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: sanitize(item, replacements) for key, item in value.items()}
    return value


def packets():
    image = Image.new("RGB", (760, 340), "#f5f3ed")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=30)
    for index, line in enumerate(
        [
            "SYNTHETIC BROWSER CHECK",
            "connection pool fields",
            "pool_limit = 18",
            "state = ready",
            "Not a production screenshot",
        ]
    ):
        draw.text((28, 20 + index * 58), line, fill="#153f38", font=font)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    common = {"sent_at": "2026-11-06T08:00:00Z", "author": "合成浏览器联调"}
    return [
        {
            **common,
            "source_id": "browser-incident",
            "text": "合成事件BROWSER_CONN_47：browser-stage-r1连接池拒绝新连接。",
        },
        {
            **common,
            "source_id": "browser-proposal",
            "reply_to": "browser-incident",
            "text": "建议把连接上限改为30个；该建议未执行、未验证。",
        },
        {
            **common,
            "source_id": "browser-verified",
            "reply_to": "browser-proposal",
            "text": "已验证：browser-stage-r1实际使用max_connections=18，合成重连样例通过；"
            "结论仅覆盖此测试环境，没有单文件容量上限记录。",
        },
        {
            **common,
            "source_id": "browser-image",
            "reply_to": "browser-verified",
            "text": "BROWSER_CONN_47浏览器联调示意图，连接池字段需读取附件原图；"
            "正文不转录图中文字。",
            "images": [
                {
                    "filename": "synthetic-browser-fields.png",
                    "base64": base64.b64encode(stream.getvalue()).decode(),
                }
            ],
        },
    ], hashlib.sha256(stream.getvalue()).hexdigest()


def private_write(path, content):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(content)


def session_factory(settings):
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    return engine, sessionmaker(engine, expire_on_commit=False)


async def child_worker(settings, calls_path):
    engine, sessions = session_factory(settings)
    provider = PilotProvider(settings, {"calls": []}, calls_path)
    runner = Runner(sessions, settings, provider, ImageStore(settings))
    processor = Processor(sessions, settings, provider, ImageStore(settings))
    try:
        while True:
            provider.phase = "browser_task"
            progressed = await runner.run_once()
            if not progressed:
                provider.phase = "processing"
                progressed = await processor.run_once()
            if not progressed:
                await asyncio.sleep(0.3)
    finally:
        engine.dispose()


def run_child(args):
    settings = Settings(_env_file=None, **json.loads(args.config.read_text()))
    if args.command == "_serve":
        uvicorn.run(
            create_app(settings),
            host="127.0.0.1",
            port=args.port,
            access_log=False,
            log_level="warning",
        )
    else:
        asyncio.run(child_worker(settings, args.calls))


def available_port(requested):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", requested))
        return listener.getsockname()[1]


async def wait_health(client, processes):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        require(all(p.poll() is None for p in processes), "browser child exited before ready")
        try:
            response = await client.get("/api/health")
            if response.status_code == 200:
                require(response.json()["provider"] == "ollama", "real Ollama provider required")
                return
        except httpx.TransportError:
            pass
        await asyncio.sleep(0.2)
    raise TimeoutError("HTTP API readiness timeout")


def collect_tasks(sessions):
    rows = []
    with sessions() as session:
        for task in session.scalars(select(Task).order_by(Task.created_at)):
            actions = session.scalars(
                select(ActionRecord)
                .where(ActionRecord.task_id == task.id)
                .order_by(ActionRecord.created_at)
            ).all()
            observations = session.scalars(
                select(Observation)
                .where(Observation.task_id == task.id)
                .order_by(Observation.created_at)
            ).all()
            answer = session.scalar(select(Answer).where(Answer.task_id == task.id))
            reviews = [o for o in observations if o.kind == "support_review"]
            model_attempts = [a for a in actions if a.kind in MODEL_KINDS]
            citation_ids = answer.citation_ids if answer else []
            checks = {
                "model_attempt_accounting": task.model_calls == len(model_attempts),
                "review_not_cited": not set(citation_ids).intersection(o.id for o in reviews),
                "normal_answer_has_valid_review": task.state != "completed"
                or bool(
                    reviews
                    and reviews[-1].content.get("valid")
                    and reviews[-1].content.get("accepted")
                ),
            }
            rows.append(
                {
                    "id": task.id,
                    "question": task.question,
                    "state": task.state,
                    "error": task.error,
                    "configuration": task.config,
                    "requested_scope": task.requested_scope,
                    "checks": checks,
                    "model_calls": task.model_calls,
                    "tool_calls": task.tool_calls,
                    "image_calls": task.image_calls,
                    "recoveries": task.recoveries,
                    "actions": [
                        {"kind": a.kind, "state": a.state, "epoch": a.epoch} for a in actions
                    ],
                    "observations": [
                        {
                            "id": o.id,
                            "kind": o.kind,
                            "content": o.content,
                            "dependencies": o.dependencies,
                        }
                        for o in observations
                    ],
                    "answer": {
                        "text": answer.text,
                        "citation_ids": citation_ids,
                        "dependencies": answer.dependencies,
                    }
                    if answer
                    else None,
                }
            )
    return rows


def stop_processes(processes):
    for process in processes:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run_browser(command, environment):
    process = subprocess.Popen(
        command,
        cwd=PROJECT / "frontend",
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=420)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


async def validate(args, report):
    version, models = await model_metadata(
        args.ollama_url, PROJECT / "docs/evidence/real-model/model-manifest.json"
    )
    report.update(ollama_version=version, models=models)
    identities = {m["name"]: m["digest"] for m in models}
    revision = (
        "weights-"
        + hashlib.sha256(json.dumps(identities, sort_keys=True).encode()).hexdigest()[:24]
    )
    schema = "browser_" + uuid.uuid4().hex
    admin, engine, created = create_engine(args.database_url), None, False
    processes, logs = [], []
    temporary = tempfile.TemporaryDirectory(prefix="lume-browser-")
    runtime = Path(temporary.name)
    try:
        with admin.begin() as connection:
            report["postgres_version"] = connection.scalar(text("SELECT version()"))
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            connection.execute(text(f"CREATE SCHEMA {schema}"))
            created = True
        scoped = (
            make_url(args.database_url)
            .update_query_dict({"options": f"-csearch_path={schema},public"})
            .render_as_string(hide_password=False)
        )
        settings = Settings(
            _env_file=None,
            database_url=scoped,
            provider="ollama",
            data_dir=runtime / "data",
            ollama_url=args.ollama_url,
            model_revision=revision,
            ocr_lang="eng",
        )
        engine, sessions = session_factory(settings)
        Base.metadata.create_all(engine, checkfirst=False)
        with sessions.begin() as session:
            _, token = create_user(session, "browser-validation", admin=True)
            session.add(RuntimeSetting(key="rules_id", value=settings.rules_id))
        token_path, config_path, calls_path = (
            runtime / name for name in ["access-token", "child-config.json", "model-calls.json"]
        )
        private_write(token_path, token + "\n")
        private_write(config_path, settings.model_dump_json())
        port = available_port(args.port)
        base_url = f"http://127.0.0.1:{port}"
        report["configuration"] = {
            k: getattr(settings, k)
            for k in [
                "rules_id",
                "task_timeout",
                "lease_seconds",
                "max_model_calls",
                "max_tool_calls",
                "max_image_calls",
                "max_context_chars",
                "retrieval_k",
                "rrf_constant",
            ]
        }
        report["http_base_url"] = base_url
        report["stage"] = "starting_http_children"
        save(args.output, report)
        for command in ["_serve", "_worker"]:
            log = (runtime / (command + ".log")).open("w")
            logs.append(log)
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "scripts.browser_validation",
                        command,
                        "--config",
                        str(config_path),
                        "--port",
                        str(port),
                        "--calls",
                        str(calls_path),
                    ],
                    cwd=PROJECT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            )
        try:
            async with httpx.AsyncClient(
                base_url=base_url,
                timeout=10,
                trust_env=False,
                headers={"Authorization": "Bearer " + token},
            ) as client:
                await wait_health(client, processes)
                report["stage"] = "http_ready"
                save(args.output, report)
                response = await client.post(
                    "/api/spaces", json={"name": "浏览器联调 · 全新合成资料"}
                )
                response.raise_for_status()
                space_id = response.json()["id"]
                messages, image_digest = packets()
                report["fixture"] = {
                    "source_ids": [m["source_id"] for m in messages],
                    "image_sha256": image_digest,
                    "kind": "synthetic-only",
                }
                response = await client.post(
                    f"/api/spaces/{space_id}/imports", json={"messages": messages}
                )
                response.raise_for_status()
                deadline = time.monotonic() + 100
                while time.monotonic() < deadline:
                    response = await client.get(f"/api/spaces/{space_id}/jobs")
                    response.raise_for_status()
                    jobs = response.json()
                    if len(jobs) == 4 and all(j["state"] == "ready" for j in jobs):
                        report["processing"] = jobs
                        report["stage"] = "synthetic_index_ready"
                        save(args.output, report)
                        break
                    require(
                        not any(j["state"] in {"failed", "superseded"} for j in jobs),
                        "synthetic browser index processing failed",
                    )
                    await asyncio.sleep(0.4)
                else:
                    raise TimeoutError("synthetic browser index readiness timeout")
            artifacts = args.output.with_name(args.output.stem + "-artifacts")
            artifacts.mkdir(exist_ok=False)
            browser_env = {
                **os.environ,
                "LUME_UI_REAL_MODELS": "1",
                "LUME_UI_BASE_URL": base_url,
                "LUME_UI_TOKEN_FILE": str(token_path),
                "LUME_UI_ARTIFACT_DIR": str(artifacts.resolve()),
            }
            report["stage"] = "browser_running"
            save(args.output, report)
            result = await asyncio.to_thread(
                run_browser,
                [
                    "npx",
                    "--no-install",
                    "playwright",
                    "test",
                    "tests/reviewed-workbench.spec.ts",
                    "--reporter=json",
                ],
                browser_env,
            )
            replacements = [
                (token, "<redacted>"),
                (str(runtime), "<runtime>"),
                (str(PROJECT), "<workspace>"),
            ]
            report["browser_exit_code"] = result.returncode
            try:
                browser_report = json.loads(result.stdout)
            except ValueError:
                browser_report = {
                    "invalid_report": True,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            save(
                args.output.with_name(args.output.stem + "-playwright.json"),
                sanitize(browser_report, replacements),
            )
            report["browser_report"] = args.output.stem + "-playwright.json"
            report["screenshots"] = [p.name for p in sorted(artifacts.glob("*.png"))]
            report["stage"] = "browser_finished"
            save(args.output, report)
            if result.returncode == 0:
                with sessions() as session:
                    answer_id = session.scalar(
                        select(Answer.id)
                        .join(Task)
                        .where(Task.state == "completed")
                        .order_by(Task.created_at)
                    )
                    before_actions = len(session.scalars(select(ActionRecord)).all())
                require(answer_id is not None, "read window needs a completed own answer")
                before_calls = len(json.loads(calls_path.read_text())["calls"])
                async with httpx.AsyncClient(
                    base_url=base_url,
                    timeout=10,
                    trust_env=False,
                    headers={"Authorization": "Bearer " + token},
                ) as client:
                    read_window = await measure_reads(
                        client,
                        [
                            "/api/health",
                            "/api/spaces",
                            f"/api/spaces/{space_id}/messages",
                            f"/api/answers/{answer_id}",
                        ],
                    )
                with sessions() as session:
                    after_actions = len(session.scalars(select(ActionRecord)).all())
                after_calls = len(json.loads(calls_path.read_text())["calls"])
                require(
                    before_actions == after_actions and before_calls == after_calls,
                    "model/action activity occurred during read-only measurement",
                )
                read_window.update(
                    model_calls_during_window=0,
                    actions_during_window=0,
                    measured_requests=288,
                    note="Synthetic local read-only endpoints; not model/system QPS",
                )
                load_path = args.output.with_name(args.output.stem + "-read-load.json")
                save(load_path, read_window)
                report["read_load_report"] = load_path.name
                report["stage"] = "read_window_finished"
                save(args.output, report)
        finally:
            stop_processes(processes)
            report["child_processes_stopped"] = all(p.poll() is not None for p in processes)
            report["tasks"] = collect_tasks(sessions)
            if calls_path.exists():
                report["model_calls"] = json.loads(calls_path.read_text())["calls"]
        require(report.get("browser_exit_code") == 0, "browser assertions did not pass")
        require(len(report["tasks"]) == 3, "expected three browser-submitted tasks")
        require(
            all(all(task["checks"].values()) for task in report["tasks"]),
            "browser SQL accounting or review checks did not pass",
        )
    finally:
        stop_processes(processes)
        report["child_processes_stopped"] = all(p.poll() is not None for p in processes)
        for log in logs:
            log.close()
        if engine is not None:
            engine.dispose()
        try:
            if created:
                with admin.begin() as connection:
                    connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            report["isolated_schema_removed"] = created
        finally:
            admin.dispose()
            temporary.cleanup()
            report["temporary_credentials_removed"] = not runtime.exists()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    runner = commands.add_parser("run")
    runner.add_argument("--database-url", default=os.environ.get("LUME_TEST_DATABASE_URL"))
    runner.add_argument("--ollama-url", default="http://127.0.0.1:11435")
    runner.add_argument("--application-baseline", required=True)
    runner.add_argument("--port", type=int, default=0)
    runner.add_argument("--output", type=Path, required=True)
    for command in ["_serve", "_worker"]:
        child = commands.add_parser(command)
        child.add_argument("--config", type=Path, required=True)
        child.add_argument("--port", type=int, required=True)
        child.add_argument("--calls", type=Path, required=True)
    args = parser.parse_args()
    if args.command != "run":
        run_child(args)
        return
    endpoint = urlparse(args.ollama_url)
    require(
        endpoint.scheme == "http"
        and endpoint.hostname in {"localhost", "127.0.0.1", "::1"}
        and not endpoint.username
        and not endpoint.password
        and not endpoint.query
        and not endpoint.fragment
        and endpoint.path in {"", "/"},
        "local Ollama endpoint required",
    )
    require(args.database_url, "LUME_TEST_DATABASE_URL required")
    require((PROJECT / "frontend/dist/index.html").exists(), "build frontend before validation")
    require(
        not subprocess.check_output(
            ["git", "diff", args.application_baseline, "--", "backend/src/lume"], cwd=PROJECT
        ),
        "application differs from frozen baseline",
    )
    require(
        not subprocess.check_output(["git", "status", "--porcelain"], cwd=PROJECT).strip(),
        "commit the validation implementation before execution",
    )
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x"):
        pass
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "scope": "new synthetic browser workflow only",
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
        ).strip(),
        "application_baseline": args.application_baseline,
        "source_dirty": False,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "browser_spec_sha256": hashlib.sha256(
            (PROJECT / "frontend/tests/reviewed-workbench.spec.ts").read_bytes()
        ).hexdigest(),
        "frontend_bundle_sha256": {
            str(path.relative_to(PROJECT / "frontend/dist")): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted((PROJECT / "frontend/dist").rglob("*"))
            if path.is_file()
        },
        "heldout_queries_executed": 0,
        "human_reviewed_queries": 0,
        "quality_scores_computed": False,
    }
    try:
        asyncio.run(validate(args, report))
    except Exception as error:
        report["fatal_error"] = type(error).__name__
    report["finished_at"] = datetime.now(UTC).isoformat()
    save(args.output, report)
    print(
        json.dumps(
            {
                k: report.get(k)
                for k in [
                    "browser_exit_code",
                    "fatal_error",
                    "isolated_schema_removed",
                    "child_processes_stopped",
                ]
            }
        )
    )
    if report.get("fatal_error"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
