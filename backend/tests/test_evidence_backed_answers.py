import pytest
from lume.knowledge import read_context, search
from lume.models import Observation, Task
from lume.schemas import AgentAction
from lume.security import DomainError

from .conftest import packet, prepare


async def test_context_reaches_verification_beyond_the_first_reply(client, system):
    imported = await prepare(
        client,
        system,
        [
            packet("incident", "BUILD_RETRY_204 初始失败"),
            packet("proposal", "建议延长重试，未执行", reply_to="incident"),
            packet("verified", "已验证：使用幂等键，重放只执行一次", reply_to="proposal"),
            packet("unrelated", "旧环境使用另一方案"),
        ],
    )
    with system.sessions() as session:
        content, dependencies = read_context(session, system.alice, imported[0]["id"], [system.a])
    assert {m["source_id"] for m in content["messages"]} == {"incident", "proposal", "verified"}
    assert len(dependencies) == 3


async def test_exact_technical_identifier_excludes_unrelated_candidates(client, system):
    await prepare(
        client,
        system,
        [
            packet("noise", "其他模块的修订验证与重试建议"),
            packet("target", "BUILD_RETRY_204 的修订验证记录"),
        ],
    )
    content, _ = await search(
        system.sessions,
        system.settings,
        system.provider,
        system.alice,
        "BUILD_RETRY_204 修订验证",
        [system.a],
    )
    assert {c["source_id"] for c in content["candidates"]} == {"target"}
    missing, _ = await search(
        system.sessions,
        system.settings,
        system.provider,
        system.alice,
        "UNRECORDED_CODE_930",
        [system.a],
    )
    assert missing["candidates"] == []


async def test_grounded_contract_rejects_unselected_freeform_numeric_answer(client, system):
    imported = await prepare(client, system, [packet(text="这是未执行建议，没有生产容量记录")])
    created = await client.post(
        "/api/tasks", json={"question": "生产容量是多少", "space_ids": [system.a]}
    )
    assert created.status_code == 202
    task_id, epoch = system.runner.claim()
    dependencies = [{"message_id": imported[0]["id"], "version": 1}]
    with system.sessions.begin() as session:
        task = session.get(Task, task_id)
        task.config = {**task.config, "answer_contract": "source-excerpts-v1"}
        observation = Observation(
            task_id=task_id,
            kind="message_context",
            content={
                "messages": [
                    {"message_id": imported[0]["id"], "text": "这是未执行建议，没有生产容量记录"}
                ]
            },
            dependencies=dependencies,
        )
        session.add(observation)
        session.flush()
    with pytest.raises(DomainError, match="EVIDENCE_REQUIRED"):
        system.runner.publish(
            task_id,
            epoch,
            AgentAction(kind="final", answer="生产容量10 GiB", citation_ids=[observation.id]),
            dependencies,
        )


async def test_reply_graph_bounds_and_does_not_cross_inactive_bridges(client, system):
    from lume.models import Message

    packets = [packet("root", "起点")]
    packets += [
        packet(f"m{i}", f"第{i}跳", reply_to="root" if i == 1 else f"m{i - 1}") for i in range(1, 7)
    ]
    imported = await prepare(client, system, packets)
    with system.sessions() as session:
        content, _ = read_context(session, system.alice, imported[0]["id"], [system.a])
        assert {m["source_id"] for m in content["messages"]} == {"root", "m1", "m2", "m3", "m4"}
        assert content["window"]["truncated"] is True
    with system.sessions.begin() as session:
        session.get(Message, imported[1]["id"]).active = False
    with system.sessions() as session:
        content, _ = read_context(session, system.alice, imported[0]["id"], [system.a])
        assert [m["source_id"] for m in content["messages"]] == ["root"]


async def test_reply_graph_deduplicates_cycle_and_limits_fanout(client, system):
    imported = await prepare(
        client,
        system,
        [
            packet("root", "起点", reply_to="child-00"),
            *[packet(f"child-{i:02}", "直接回复", reply_to="root") for i in range(15)],
        ],
    )
    with system.sessions() as session:
        content, dependencies = read_context(session, system.alice, imported[0]["id"], [system.a])
    assert len(content["messages"]) == len(dependencies) == 12
    assert len({d["message_id"] for d in dependencies}) == 12
    assert content["window"]["truncated"] is True


async def test_ambiguous_native_index_and_cross_space_replies_are_not_followed(client, system):
    imported = await prepare(
        client,
        system,
        [
            packet("root", "起点", native_index="duplicate"),
            packet("other", "同索引", native_index="duplicate"),
            packet("reply", "无法确定父亲", reply_to="duplicate", reply_kind="native_index"),
        ],
    )
    response = await client.post(
        f"/api/spaces/{system.b}/imports",
        headers=system.bob_headers,
        json={"messages": [packet("foreign", "跨空间", reply_to="root")]},
    )
    assert response.status_code == 202
    with system.sessions() as session:
        for index in (0, 2):
            content, _ = read_context(session, system.alice, imported[index]["id"], [system.a])
            assert len(content["messages"]) == 1
            assert content["window"]["ambiguous_links"] is True
        with pytest.raises(DomainError, match="NOT_FOUND"):
            read_context(session, system.alice, imported[0]["id"], [system.b])


def test_anchor_matching_is_exact_case_folded_and_does_not_gate_field_names():
    from lume.providers import technical_anchors

    assert technical_anchors("BUILD_RETRY_204 或 atlas-staging-r3，pool_size v1.8") == [
        "build_retry_204",
        "atlas-staging-r3",
    ]
    assert technical_anchors("pool_size 修改建议") == []


@pytest.mark.parametrize(
    "selection,kind,content,owner,code",
    [
        ({"message_id": "invented"}, "message_context", {"messages": []}, "t", "INVALID_EVIDENCE"),
        ({"message_id": "m"}, "candidate_only", {"candidates": []}, "t", "INVALID_EVIDENCE"),
        (
            {},
            "image_observation",
            {"semantic": False, "text": "非语义回放"},
            "t",
            "INVALID_EVIDENCE",
        ),
        ({}, "image_observation", {"semantic": True, "text": "   "}, "t", "INVALID_EVIDENCE"),
        (
            {},
            "image_observation",
            {"semantic": True, "text": "原图"},
            "foreign",
            "INVALID_EVIDENCE",
        ),
        (
            {"message_id": "m"},
            "message_context",
            {"messages": [{"message_id": "m", "text": "字" * 12000}]},
            "t",
            "EVIDENCE_TOO_LARGE",
        ),
    ],
)
def test_evidence_rejects_wrong_membership_kind_owner_empty_image_and_oversize(
    selection, kind, content, owner, code
):
    from types import SimpleNamespace

    from lume.evidence import render_evidence
    from lume.schemas import EvidenceSelection

    observation = SimpleNamespace(id="o", task_id=owner, kind=kind, content=content)
    with pytest.raises(DomainError, match=code):
        render_evidence(
            "t", [EvidenceSelection(observation_id="o", **selection)], {"o": observation}
        )


async def test_publication_renders_whole_stored_text_and_overrides_model_prose(client, system):
    from lume.evidence import INSUFFICIENT_TEXT
    from lume.models import Answer
    from lume.schemas import EvidenceSelection
    from sqlalchemy import select

    text = "仅测试环境，建议容量10 GiB；未执行，不能代表生产结论。"
    imported = await prepare(client, system, [packet(text=text)])
    for insufficient in (False, True):
        await client.post("/api/tasks", json={"question": "生产容量", "space_ids": [system.a]})
        task_id, epoch = system.runner.claim()
        with system.sessions.begin() as session:
            task = session.get(Task, task_id)
            task.config = {**task.config, "answer_contract": "source-excerpts-v1"}
            ob = Observation(
                task_id=task_id,
                kind="message_context",
                dependencies=[],
                content={
                    "messages": [{"message_id": imported[0]["id"], "text": text}],
                },
            )
            session.add(ob)
            session.flush()
        system.runner.publish(
            task_id,
            epoch,
            AgentAction(
                kind="final",
                answer="生产容量1000 GiB",
                insufficient=insufficient,
                evidence=[EvidenceSelection(observation_id=ob.id, message_id=imported[0]["id"])],
            ),
            [{"message_id": imported[0]["id"], "version": 1}],
        )
        with system.sessions() as session:
            answer = session.scalar(select(Answer).where(Answer.task_id == task_id))
            assert "1000 GiB" not in answer.text
            if insufficient:
                assert answer.text == INSUFFICIENT_TEXT and answer.citation_ids == []
            else:
                assert text in answer.text and answer.citation_ids == [ob.id]


async def test_ollama_contract_is_frozen_server_side(client, system):
    import httpx
    from lume.api import create_app
    from lume.config import Settings

    app = create_app(Settings(_env_file=None, provider="ollama"), system.sessions)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=system.alice_headers
    ) as api:
        response = await api.post("/api/tasks", json={"question": "资料", "space_ids": [system.a]})
        assert response.status_code == 202
        with system.sessions() as session:
            task = session.get(Task, response.json()["id"])
            assert task.config["answer_contract"] == "source-excerpts-v1"
        response = await api.post(
            "/api/tasks",
            json={"question": "资料", "space_ids": [system.a], "answer_contract": "legacy"},
        )
        assert response.status_code == 422


def test_actual_image_selection_renders_stored_observation_and_deduplicates():
    from types import SimpleNamespace

    from lume.evidence import render_evidence
    from lume.schemas import EvidenceSelection

    ob = SimpleNamespace(
        id="o",
        task_id="t",
        kind="image_observation",
        content={"semantic": True, "text": "圆点为紫色，位于目标卡片左端。"},
    )
    selection = EvidenceSelection(observation_id="o")
    text, ids = render_evidence("t", [selection, selection], {"o": ob})
    assert text.count(ob.content["text"]) == 1
    assert ids == ["o"]


async def test_wire_answers_convert_only_to_selections_and_insufficient(monkeypatch):
    import json

    from lume.config import Settings
    from lume.providers import OllamaProvider

    provider = OllamaProvider(Settings(_env_file=None))
    response = {"kind": "answer", "evidence": [{"observation_id": "o", "message_id": "m"}]}

    async def reply(endpoint, payload):
        return {"message": {"content": json.dumps(response)}}

    monkeypatch.setattr(provider, "_post", reply)
    action = AgentAction.model_validate(await provider.plan("资料", [], []))
    assert action.evidence[0].message_id == "m"
    response = {"kind": "insufficient"}
    action = AgentAction.model_validate(await provider.plan("资料", [], []))
    assert action.insufficient and not action.evidence
    response = {
        "kind": "answer",
        "evidence": [{"observation_id": "o", "message_id": "m"}],
        "answer": "添加的数字1000",
    }
    with pytest.raises(ValueError):
        await provider.plan("资料", [], [])
