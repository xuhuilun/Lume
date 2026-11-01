import asyncio
import base64
import json
import time
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from lume.agent import Runner, StaleRun
from lume.demo import sample_messages
from lume.models import (
    Answer,
    Artifact,
    ImageAsset,
    Message,
    Observation,
    ProcessingJob,
    RuntimeSetting,
    Task,
    now,
)
from lume.processing import Processor
from lume.providers import DemoProvider
from lume.qq import key_for, verify_signature
from lume.schemas import AgentAction
from lume.security import DomainError
from sqlalchemy import func, select

from .conftest import ask, packet, prepare


async def test_real_pgvector_ingestion_and_source_grounded_answer(client, system):
    await prepare(client, system, [m.model_dump(mode="json") for m in sample_messages()])
    status = await ask(client, system)
    assert status["state"] == "completed", status
    answer = (await client.get("/api/answers/" + status["answer_id"])).json()
    assert "20" in answer["text"] and answer["citation_ids"]
    assert len(answer["dependencies"]) == 4
    with system.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Artifact)) == 4
        image = session.scalar(select(ImageAsset))
        assert image.blob and image.digest
        # OCR is a real local executable when available, not a prefilled annotation.
        if image.error is None:
            assert "20" in image.ocr_text


async def test_idempotency_and_new_version_invalidate_answer(client, system):
    imported = await prepare(client, system)
    repeated = await client.post(f"/api/spaces/{system.a}/imports", json={"messages": [packet()]})
    assert repeated.json()["messages"][0]["duplicate"]
    status = await ask(client, system)
    assert status["state"] == "completed", status
    await client.post(
        f"/api/spaces/{system.a}/imports",
        json={"messages": [packet(text="E_CONN_42 corrected: pool_size=30")]},
    )
    assert (await client.get("/api/answers/" + status["answer_id"])).status_code == 409
    with system.sessions() as session:
        assert session.get(Message, imported[0]["id"]).version == 2


async def test_admin_role_does_not_grant_other_space_read(client, system):
    assert (await client.get(f"/api/spaces/{system.b}/messages")).status_code == 404
    result = await client.post("/api/tasks", json={"question": "secret", "space_ids": [system.b]})
    assert result.status_code == 403
    assert (await client.get("/api/me", headers={"Authorization": "Bearer bad"})).status_code == 401


async def test_cross_user_task_is_not_disclosed(client, system):
    task = await client.post("/api/tasks", json={"question": "q", "space_ids": [system.a]})
    path = "/api/tasks/" + task.json()["id"]
    hidden = await client.get(path, headers=system.bob_headers)
    absent = await client.get("/api/tasks/missing", headers=system.bob_headers)
    assert hidden.status_code == absent.status_code == 404
    assert hidden.json() == absent.json()


class FirstCandidatePlanner(DemoProvider):
    async def plan(self, question, observations, history):
        candidates = [o for o in observations if o["kind"] == "candidate_only"]
        contexts = [o for o in observations if o["kind"] == "message_context"]
        if not candidates:
            return {"kind": "search", "query": question}
        if not contexts:
            return {
                "kind": "read_context",
                "target_id": candidates[0]["content"]["candidates"][0]["message_id"],
            }
        return {"kind": "final", "answer": "来自已读记录", "citation_ids": [contexts[0]["id"]]}


async def test_history_inherits_even_uncited_candidate_source(client, system):
    system.runner = Runner(system.sessions, system.settings, FirstCandidatePlanner(), system.store)
    await prepare(client, system, [packet("one"), packet("two", text="Other E_CONN_42 evidence")])
    first = await ask(client, system)
    with system.sessions() as session:
        original = session.get(Answer, first["answer_id"])
        cited = session.get(Observation, original.citation_ids[0])
        cited_messages = {m["message_id"] for m in cited.content["messages"]}
        uncited = {d["message_id"] for d in original.dependencies} - cited_messages
        assert len(uncited) == 1 and len(original.citation_ids) == 1
    followup = await ask(client, system, history_ids=[first["answer_id"]])
    with system.sessions.begin() as session:
        assert len(session.get(Answer, followup["answer_id"]).dependencies) == 2
        session.get(Message, uncited.pop()).active = False
    assert (await client.get("/api/answers/" + first["answer_id"])).status_code == 409
    assert (await client.get("/api/answers/" + followup["answer_id"])).status_code == 409


async def test_candidate_only_cannot_be_cited(client, system):
    await prepare(client, system)
    task = (await client.post("/api/tasks", json={"question": "q", "space_ids": [system.a]})).json()
    task_id, epoch = system.runner.claim()
    with system.sessions.begin() as session:
        observation = Observation(
            task_id=task_id, kind="candidate_only", content={}, dependencies=[]
        )
        session.add(observation)
        session.flush()
        oid = observation.id
    with pytest.raises(DomainError, match="INVALID_CITATION"):
        system.runner.publish(
            task_id, epoch, AgentAction(kind="final", answer="unverified", citation_ids=[oid]), []
        )
    assert task["id"] == task_id


class BadPlanner(DemoProvider):
    async def plan(self, question, observations, history):
        return {"kind": "run_shell", "command": "ignored"}


async def test_invalid_actions_exhaust_model_budget(client, system):
    task = (await client.post("/api/tasks", json={"question": "q", "space_ids": [system.a]})).json()
    runner = Runner(system.sessions, system.settings, BadPlanner(), system.store)
    await runner.run_once()
    status = (await client.get("/api/tasks/" + task["id"])).json()
    assert status["state"] == "limited"
    assert status["model_calls"] == system.settings.max_model_calls
    assert status["tool_calls"] == 0


class BlockingPlanner(DemoProvider):
    def __init__(self):
        self.entered, self.release = asyncio.Event(), asyncio.Event()

    async def plan(self, question, observations, history):
        self.entered.set()
        await self.release.wait()
        return await super().plan(question, observations, history)


async def test_cancel_while_model_in_flight_blocks_new_actions(client, system):
    provider = BlockingPlanner()
    runner = Runner(system.sessions, system.settings, provider, system.store)
    task = (await client.post("/api/tasks", json={"question": "q", "space_ids": [system.a]})).json()
    execution = asyncio.create_task(runner.run_once())
    await asyncio.wait_for(provider.entered.wait(), 3)
    assert (await client.post("/api/tasks/" + task["id"] + "/cancel")).json()[
        "state"
    ] == "cancel_requested"
    provider.release.set()
    await execution
    status = (await client.get("/api/tasks/" + task["id"])).json()
    assert status["state"] == "cancelled"
    assert status["model_calls"] == 1 and status["tool_calls"] == 0


async def test_expired_lease_without_successor_cannot_reserve_or_publish(client, system):
    task = (await client.post("/api/tasks", json={"question": "q", "space_ids": [system.a]})).json()
    task_id, epoch = system.runner.claim()
    system.runner.reserve(task_id, epoch, "model")
    with system.sessions.begin() as session:
        row = session.get(Task, task_id)
        row.lease_until = now() - timedelta(seconds=1)
    with pytest.raises(StaleRun):
        system.runner.reserve(task_id, epoch, "model")
    with pytest.raises(StaleRun):
        system.runner.publish(
            task_id, epoch, AgentAction(kind="final", answer="x", insufficient=True), []
        )
    _, new_epoch = system.runner.claim()
    assert new_epoch > epoch
    with system.sessions() as session:
        assert session.get(Task, task_id).model_calls == 1
    assert task["id"] == task_id


class BlockingEmbedding(DemoProvider):
    def __init__(self):
        self.entered, self.release = asyncio.Event(), asyncio.Event()

    async def embed(self, text):
        self.entered.set()
        await self.release.wait()
        return await super().embed(text)


async def test_rules_changed_during_processing_reject_old_publish(client, system):
    await client.post(f"/api/spaces/{system.a}/imports", json={"messages": [packet()]})
    provider = BlockingEmbedding()
    processor = Processor(system.sessions, system.settings, provider, system.store)
    execution = asyncio.create_task(processor.run_once())
    await asyncio.wait_for(provider.entered.wait(), 3)
    with system.sessions.begin() as session:
        session.get(RuntimeSetting, "rules_id").value = "new-generation"
    provider.release.set()
    await execution
    with system.sessions() as session:
        assert session.scalar(select(ProcessingJob)).state == "superseded"
        assert session.scalar(select(func.count()).select_from(Artifact)) == 0


def test_official_qq_key_derivation_and_raw_body_signature():
    secret = "naOC0ocQE3shWLAfffVLB1rhYPG7"
    public = key_for(secret).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    assert list(public) == [
        215,
        195,
        98,
        254,
        120,
        174,
        248,
        31,
        242,
        50,
        135,
        180,
        147,
        98,
        139,
        93,
        176,
        42,
        60,
        79,
        227,
        11,
        33,
        94,
        77,
        25,
        96,
        155,
        93,
        118,
        103,
        58,
    ]
    body = b'{"op":0,"d":{},"t":"GATEWAY_EVENT_NAME"}'
    timestamp = "1725442341"
    signature = key_for(secret).sign(timestamp.encode() + body).hex()
    verify_signature(secret, timestamp, body, signature, clock=int(timestamp))
    with pytest.raises(DomainError):
        verify_signature(secret, timestamp, body + b" ", signature, clock=int(timestamp))
    with pytest.raises(DomainError):
        verify_signature(secret, timestamp, body, signature, clock=int(timestamp) + 301)


async def test_qq_callback_signature_whitelist_and_dedup(client, system):
    payload = {
        "op": 0,
        "id": "synthetic-event",
        "t": "GROUP_AT_MESSAGE_CREATE",
        "d": {
            "id": "qq-one",
            "group_openid": "group-A",
            "content": "test event",
            "timestamp": "2026-11-01T08:00:00Z",
            "author": {"member_openid": "synthetic-author"},
        },
    }
    raw = json.dumps(payload).encode()
    timestamp = str(int(time.time()))
    signature = key_for(system.settings.qq_secret).sign(timestamp.encode() + raw).hex()
    headers = {
        "X-Bot-Appid": "test-app",
        "X-Signature-Timestamp": timestamp,
        "X-Signature-Ed25519": signature,
        "Content-Type": "application/json",
    }
    path = "/integrations/qq/" + system.settings.qq_webhook_token
    assert (await client.post(path, content=raw, headers=headers)).status_code == 200
    assert (await client.post(path, content=raw, headers=headers)).status_code == 200
    assert (await client.post(path, content=raw + b" ", headers=headers)).status_code == 401
    assert (
        await client.post("/integrations/qq/wrong", content=raw, headers=headers)
    ).status_code == 404
    with system.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Message)) == 1


async def test_invalid_image_rejected_and_images_require_current_access(client, system):
    invalid = packet(images=[{"filename": "x.png", "base64": base64.b64encode(b"bad").decode()}])
    assert (
        await client.post(f"/api/spaces/{system.a}/imports", json={"messages": [invalid]})
    ).status_code == 422
    await prepare(client, system, [sample_messages()[-1].model_dump(mode="json")])
    with system.sessions() as session:
        image = session.scalar(select(ImageAsset))
        image_id = image.id
    result = await client.get("/api/images/" + image_id)
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert (
        await client.get("/api/images/" + image_id, headers=system.bob_headers)
    ).status_code == 404


async def test_qq_challenge_requires_registration_credential(client, system):
    body = {"op": 13, "d": {"plain_token": "synthetic-challenge", "event_ts": "1725442341"}}
    headers = {"X-Bot-Appid": system.settings.qq_app_id}
    response = await client.post(
        "/integrations/qq/" + system.settings.qq_webhook_token, json=body, headers=headers
    )
    assert response.status_code == 200
    result = response.json()
    key_for(system.settings.qq_secret).public_key().verify(
        bytes.fromhex(result["signature"]), b"1725442341synthetic-challenge"
    )
    assert (
        await client.post("/integrations/qq/public", json=body, headers=headers)
    ).status_code == 404


@pytest.mark.parametrize(
    "url",
    ["http://multimedia.nt.qq.com.cn/file", "https://127.0.0.1/a", "https://untrusted.invalid/a"],
)
async def test_remote_image_origin_is_rejected_without_network(system, url):
    with pytest.raises(DomainError, match="REMOTE_IMAGE_REJECTED"):
        await system.store.download(url)


async def test_chunked_body_is_bounded_before_parsing(system):
    import httpx
    from lume.api import create_app

    settings = system.settings.model_copy(update={"max_request_bytes": 32})
    app = create_app(settings, system.sessions)

    async def chunks():
        yield b"a" * 20
        yield b"b" * 20

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/tasks", content=chunks())
    assert response.status_code == 413
    assert response.json()["code"] == "INPUT_TOO_LARGE"


async def test_expired_processing_owner_does_not_start_external_work(client, system):
    response = await client.post(f"/api/spaces/{system.a}/imports", json={"messages": [packet()]})
    assert response.status_code == 202
    job_id, epoch = system.processor.claim()
    with system.sessions.begin() as session:
        session.get(ProcessingJob, job_id).lease_until = now() - timedelta(seconds=1)
    provider = BlockingEmbedding()
    processor = Processor(system.sessions, system.settings, provider, system.store)
    await processor.process(job_id, epoch)
    assert not provider.entered.is_set()
    with system.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Artifact)) == 0


class BlockBeforeFinal(DemoProvider):
    def __init__(self):
        self.entered, self.release = asyncio.Event(), asyncio.Event()

    async def plan(self, question, observations, history):
        if any(o["kind"] == "message_context" for o in observations):
            self.entered.set()
            await self.release.wait()
        return await super().plan(question, observations, history)


async def test_source_change_during_model_call_blocks_answer_publication(client, system):
    message = (await prepare(client, system))[0]
    provider = BlockBeforeFinal()
    runner = Runner(system.sessions, system.settings, provider, system.store)
    task = (
        await client.post("/api/tasks", json={"question": "E_CONN_42", "space_ids": [system.a]})
    ).json()
    execution = asyncio.create_task(runner.run_once())
    await asyncio.wait_for(provider.entered.wait(), 3)
    await client.post("/api/messages/" + message["id"] + "/deactivate")
    provider.release.set()
    await execution
    status = (await client.get("/api/tasks/" + task["id"])).json()
    assert status["state"] == "failed" and status["answer_id"] is None


async def test_natural_lease_expiry_allows_recovery_before_absolute_deadline(client, system):
    system.settings.lease_seconds = 1
    system.settings.task_timeout = 6
    result = await client.post("/api/tasks", json={"question": "q", "space_ids": [system.a]})
    task_id, old_epoch = system.runner.claim()
    assert result.json()["id"] == task_id
    system.runner.reserve(task_id, old_epoch, "model")
    with system.sessions() as session:
        deadline = session.get(Task, task_id).deadline
    # Simulate a crashed owner by not starting its heartbeat, without editing the lease.
    await asyncio.sleep(1.1)
    recovered_id, new_epoch = system.runner.claim()
    assert recovered_id == task_id and new_epoch > old_epoch
    await system.runner.execute(task_id, new_epoch)
    with system.sessions() as session:
        task = session.get(Task, task_id)
        assert task.state == "insufficient" and task.deadline == deadline
        assert task.model_calls > 1


async def test_heartbeat_keeps_live_owner_from_being_reclaimed(client, system):
    system.settings.lease_seconds = 1
    system.settings.task_timeout = 6
    await client.post("/api/tasks", json={"question": "q", "space_ids": [system.a]})
    provider = BlockingPlanner()
    runner = Runner(system.sessions, system.settings, provider, system.store)
    execution = asyncio.create_task(runner.run_once())
    await asyncio.wait_for(provider.entered.wait(), 3)
    await asyncio.sleep(1.2)
    assert runner.claim() is None
    provider.release.set()
    await execution


async def test_changed_chat_model_cannot_silently_run_a_frozen_task(client, system):
    task = (await client.post("/api/tasks", json={"question": "q", "space_ids": [system.a]})).json()
    system.settings.chat_model = "a-different-chat-model"
    await system.runner.run_once()
    status = (await client.get("/api/tasks/" + task["id"])).json()
    assert status["state"] == "failed" and status["error"] == "CONFIG_CHANGED"
    assert status["model_calls"] == 0
