import pytest
from lume.models import Observation, Task
from lume.schemas import AgentAction, EvidenceSelection
from lume.security import DomainError

from .conftest import packet, prepare


async def test_normal_answer_cannot_publish_related_excerpt_without_support_review(client, system):
    imported = await prepare(
        client, system, [packet(text="仅测试环境分片尺寸为5 MiB，没有文件上限记录。")]
    )
    await client.post(
        "/api/tasks", json={"question": "生产单文件容量上限是多少GiB？", "space_ids": [system.a]}
    )
    task_id, epoch = system.runner.claim()
    dependencies = [{"message_id": imported[0]["id"], "version": 1}]
    with system.sessions.begin() as session:
        task = session.get(Task, task_id)
        task.config = {**task.config, "answer_contract": "reviewed-excerpts-v1"}
        observation = Observation(
            task_id=task_id,
            kind="message_context",
            dependencies=dependencies,
            content={
                "messages": [
                    {
                        "message_id": imported[0]["id"],
                        "text": "仅测试环境分片尺寸为5 MiB，没有文件上限记录。",
                    }
                ]
            },
        )
        session.add(observation)
        session.flush()
    with pytest.raises(DomainError, match="SUPPORT_REVIEW_REQUIRED"):
        system.runner.publish(
            task_id,
            epoch,
            AgentAction(
                kind="final",
                answer="所选原文",
                citation_ids=[observation.id],
                evidence=[
                    EvidenceSelection(observation_id=observation.id, message_id=imported[0]["id"])
                ],
            ),
            dependencies,
        )


def supported_review(text="同环境已验证：连接上限为24个。"):
    quote = {"source": "S1", "quote": text}
    return {
        name: {"verdict": "supported", "quotes": [quote]}
        for name in ("fact", "unit", "scope", "status")
    }


def selected_source(text="同环境已验证：连接上限为24个。"):
    return [
        {
            "source": "S1",
            "kind": "message_context",
            "text": text,
            "sent_at": None,
            "observation_id": "o",
            "message_id": "m",
            "heading": "消息 m",
        }
    ]


@pytest.mark.parametrize("dimension", ["fact", "unit", "scope", "status"])
@pytest.mark.parametrize("verdict", ["unsupported", "uncertain"])
def test_any_unsupported_required_dimension_cannot_pass(dimension, verdict):
    from lume.sufficiency import validate_assessment

    review = supported_review()
    review[dimension] = {"verdict": verdict, "quotes": []}
    _, issues, accepted = validate_assessment(review, selected_source())
    assert not issues and accepted is False


@pytest.mark.parametrize(
    "mutation,issue",
    [
        ("fabricated_quote", "INVALID_SUPPORT_QUOTE"),
        ("wrong_label", "INVALID_SUPPORT_QUOTE"),
        ("fact_inapplicable", "INVALID_REVIEW_FORMAT"),
        ("missing_dimension", "INVALID_REVIEW_FORMAT"),
        ("empty_support_quote", "INVALID_REVIEW_FORMAT"),
    ],
)
def test_malformed_or_unbound_review_is_not_a_valid_rejection(mutation, issue):
    from lume.sufficiency import validate_assessment

    review = supported_review()
    if mutation == "fabricated_quote":
        review["fact"]["quotes"][0]["quote"] = "不存在的生产容量1000GiB"
    elif mutation == "wrong_label":
        review["fact"]["quotes"][0]["source"] = "S2"
    elif mutation == "fact_inapplicable":
        review["fact"] = {"verdict": "not_required", "quotes": []}
    elif mutation == "missing_dimension":
        del review["scope"]
    else:
        review["fact"]["quotes"] = []
    _, issues, accepted = validate_assessment(review, selected_source())
    assert issues == [issue] and accepted is False


def test_complete_support_and_non_numeric_question_can_pass():
    from lume.sufficiency import validate_assessment

    text = "同环境已确认：feature_gate=true。"
    review = supported_review(text)
    review["unit"] = {"verdict": "not_required", "quotes": []}
    canonical, issues, accepted = validate_assessment(review, selected_source(text))
    assert canonical and not issues and accepted


async def setup_review_task(client, system, text="同环境已验证：连接上限为24个。"):
    from lume.sufficiency import CONTRACT

    imported = await prepare(client, system, [packet(text=text)])
    response = await client.post(
        "/api/tasks", json={"question": "同环境验证的连接上限是多少？", "space_ids": [system.a]}
    )
    task_id = response.json()["id"]
    dependencies = [{"message_id": imported[0]["id"], "version": 1}]
    with system.sessions.begin() as session:
        task = session.get(Task, task_id)
        task.config = {**task.config, "answer_contract": CONTRACT}
        ob = Observation(
            task_id=task_id,
            kind="message_context",
            dependencies=dependencies,
            content={"messages": [{"message_id": imported[0]["id"], "text": text}]},
        )
        session.add(ob)
        session.flush()
    action = AgentAction(
        kind="final",
        answer="不能直接发布此自由文本",
        evidence=[
            EvidenceSelection(observation_id=ob.id, message_id=imported[0]["id"]),
        ],
    )
    return task_id, action, dependencies


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("supported", "completed"),
        ("unsupported", "insufficient"),
        ("invalid", "failed"),
        ("network", "failed"),
        ("budget", "limited"),
        ("revoked", "failed"),
        ("source_disabled", "failed"),
        ("cancelled", "cancelled"),
    ],
)
async def test_review_execution_and_failure_states_stay_distinct(client, system, mode, expected):
    import httpx
    from lume.models import ActionRecord, Answer, Grant, Message
    from sqlalchemy import select

    task_id, action, _ = await setup_review_task(client, system)
    calls = []

    async def plan(*args, **kwargs):
        return action.model_dump()

    async def assess(question, sources, **kwargs):
        calls.append(sources)
        review = supported_review()
        if mode == "unsupported":
            review["fact"] = {"verdict": "unsupported", "quotes": []}
        if mode == "invalid":
            review["fact"]["quotes"][0]["quote"] = "虚构引文"
        if mode == "network":
            raise httpx.ReadTimeout("synthetic transport interruption")
        if mode == "revoked":
            with system.sessions.begin() as session:
                session.get(Grant, (system.alice, system.a)).read = False
        if mode == "source_disabled":
            with system.sessions.begin() as session:
                session.get(Message, sources[0]["message_id"]).active = False
        if mode == "cancelled":
            with system.sessions.begin() as session:
                session.get(Task, task_id).state = "cancel_requested"
        return review

    system.provider.plan, system.provider.assess_support = plan, assess
    if mode == "budget":
        with system.sessions.begin() as session:
            task = session.get(Task, task_id)
            task.config = {**task.config, "max_model_calls": 1}
    await system.runner.run_once()
    with system.sessions() as session:
        task = session.get(Task, task_id)
        assert task.state == expected
        assert task.model_calls == (1 if mode == "budget" else 2)
        assert task.tool_calls == 0
        reviews = session.scalars(
            select(Observation).where(
                Observation.task_id == task_id, Observation.kind == "support_review"
            )
        ).all()
        answer = session.scalar(select(Answer).where(Answer.task_id == task_id))
        attempts = session.scalars(
            select(ActionRecord).where(
                ActionRecord.task_id == task_id, ActionRecord.kind == "support_review"
            )
        ).all()
        if mode in {"supported", "unsupported"}:
            assert len(reviews) == 1 and reviews[0].content["valid"]
            assert answer and answer.dependencies
            assert "自由文本" not in answer.text
            assert reviews[0].id not in answer.citation_ids
        else:
            assert answer is None
        if mode == "invalid":
            assert task.error == "SUPPORT_REVIEW_INVALID"
            assert reviews[0].content["valid"] is False
        assert len(attempts) == (0 if mode == "budget" else 1)


async def test_publish_revalidates_review_binding_ownership_and_verdict(client, system):
    from lume.evidence import selected_sources
    from lume.sufficiency import CONTRACT, review_binding

    task_id, action, dependencies = await setup_review_task(client, system)
    assert system.runner.claim()[0] == task_id
    with system.sessions.begin() as session:
        task = session.get(Task, task_id)
        epoch = task.epoch
        ob = session.get(Observation, action.evidence[0].observation_id)
        sources = selected_sources(task_id, action.evidence, {ob.id: ob})
        review = Observation(
            task_id=task_id,
            kind="support_review",
            dependencies=dependencies,
            content={
                "contract": CONTRACT,
                "binding": "forged",
                "assessment": supported_review(),
                "accepted": True,
            },
        )
        session.add(review)
        session.flush()
    with pytest.raises(DomainError, match="INVALID_SUPPORT_REVIEW"):
        system.runner.publish(task_id, epoch, action, dependencies, review_id=review.id)
    with system.sessions.begin() as session:
        row = session.get(Observation, review.id)
        raw = supported_review()
        raw["fact"] = {"verdict": "unsupported", "quotes": []}
        row.content = {
            **row.content,
            "binding": review_binding(task.question, False, sources),
            "assessment": raw,
            "accepted": True,
        }
    with pytest.raises(DomainError, match="SUPPORT_NOT_ESTABLISHED"):
        system.runner.publish(task_id, epoch, action, dependencies, review_id=review.id)

    other = await client.post("/api/tasks", json={"question": "其他任务", "space_ids": [system.a]})
    with system.sessions.begin() as session:
        row = session.get(Observation, review.id)
        row.task_id = other.json()["id"]
        row.content = {**row.content, "assessment": supported_review()}
    with pytest.raises(DomainError, match="INVALID_SUPPORT_REVIEW"):
        system.runner.publish(task_id, epoch, action, dependencies, review_id=review.id)


async def test_review_generation_cannot_mark_requested_fact_as_inapplicable(monkeypatch):
    from lume.config import Settings
    from lume.providers import OllamaProvider

    provider = OllamaProvider(Settings(_env_file=None))

    async def response(endpoint, payload):
        schema = payload["format"]
        fact_name = schema["properties"]["fact"]["$ref"].split("/")[-1]
        assert "not_required" not in schema["$defs"][fact_name]["properties"]["verdict"]["enum"]
        return {"message": {"content": "{}"}}

    monkeypatch.setattr(provider, "_post", response)
    await provider.assess_support("连接上限", selected_source())


def test_literal_environment_scope_blocks_a_false_positive_model_review():
    from lume.sufficiency import scope_constraints, validate_assessment

    text = "orion-qa-r9 已验证连接上限为24个。"
    sources = selected_source(text)
    raw = supported_review(text)
    assert scope_constraints("orion-prod已配置的连接上限？", sources)["missing"] == ["orion-prod"]
    _, issues, accepted = validate_assessment(raw, sources, "orion-prod已配置的连接上限？")
    assert not issues and not accepted
    assert validate_assessment(raw, sources, "orion-qa-r9的连接上限？")[2]


def test_quote_options_only_contain_original_literal_bounded_spans():
    from lume.sufficiency import quote_options

    text = "甲" * 800 + "。环境x；" + "乙" * 500
    assert all(0 < len(s) <= 400 and s in text for s in quote_options(text))


async def test_review_wire_quotes_are_literal_source_choices(monkeypatch):
    from lume.config import Settings
    from lume.providers import OllamaProvider

    provider = OllamaProvider(Settings(_env_file=None))
    sources = selected_source()

    async def response(endpoint, payload):
        variants = payload["format"]["$defs"]["SupportQuote"]["oneOf"]
        assert variants[0]["properties"]["source"]["const"] == "S1"
        assert variants[0]["properties"]["quote"]["enum"] == [sources[0]["text"]]
        assert "observation_id" not in payload["messages"][1]["content"]
        return {"message": {"content": "{}"}}

    monkeypatch.setattr(provider, "_post", response)
    await provider.assess_support("连接上限", sources)


@pytest.mark.parametrize(
    "question", ["test-driven 开发为什么先写测试？", "run-integration-tests 如何运行？"]
)
def test_common_hyphenated_terms_are_not_environment_requirements(question):
    from lume.sufficiency import scope_constraints

    assert scope_constraints(question, selected_source())["required"] == []
