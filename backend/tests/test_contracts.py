import json
import math

import pytest
from lume.config import Settings
from lume.models import Observation, Task
from lume.providers import OllamaProvider, action_schema
from sqlalchemy import select

from .conftest import prepare


async def test_frozen_retrieval_configuration_is_used(client, system):
    await prepare(client, system)
    task = (
        await client.post(
            "/api/tasks",
            json={
                "question": "E_CONN_42",
                "space_ids": [system.a],
            },
        )
    ).json()
    with system.sessions.begin() as session:
        row = session.get(Task, task["id"])
        row.config = {**row.config, "rrf_constant": 7, "retrieval_k": 1}
    await system.runner.run_once()
    with system.sessions() as session:
        observation = session.scalar(
            select(Observation).where(
                Observation.task_id == task["id"],
                Observation.kind == "candidate_only",
            )
        )
        candidate = observation.content["candidates"][0]
        assert candidate["ranks"] == {"lexical": 1, "vector": 1}
        assert candidate["score"] == pytest.approx(2 / 8)


async def test_ollama_embedding_contract_rejects_invalid_vectors(system, monkeypatch):
    provider = OllamaProvider(system.settings)

    async def invalid(endpoint, payload):
        assert endpoint == "/api/embed" and payload["truncate"] is False
        return {"embeddings": [[math.nan, 0.0]]}

    monkeypatch.setattr(provider, "_post", invalid)
    with pytest.raises(ValueError, match="Invalid embedding"):
        await provider.embed("test")

    async def valid(endpoint, payload):
        return {"embeddings": [[0.25, 0.75]]}

    monkeypatch.setattr(provider, "_post", valid)
    assert await provider.embed("test") == [0.25, 0.75]


async def test_ollama_first_decision_cannot_generate_an_invented_image_target(monkeypatch):
    provider = OllamaProvider(Settings(_env_file=None))

    async def reply(endpoint, payload):
        assert endpoint == "/api/chat" and payload["think"] is False
        variants = payload["format"]["oneOf"]
        assert len(variants) == 1
        assert variants[0]["properties"]["kind"]["const"] == "search"
        assert "query" in variants[0]["required"]
        assert variants[0]["additionalProperties"] is False
        return {"message": {"content": json.dumps({"kind": "search", "query": "E_CONN_42"})}}

    monkeypatch.setattr(provider, "_post", reply)
    assert (await provider.plan("E_CONN_42如何处理", [], []))["kind"] == "search"


def test_generation_targets_and_citations_use_distinct_current_observation_id_sets():
    observations = [
        {
            "id": "candidate-observation",
            "kind": "candidate_only",
            "content": {
                "candidates": [{"message_id": "m1"}, {"message_id": "m2"}],
            },
        },
        {
            "id": "read-observation",
            "kind": "message_context",
            "content": {
                "messages": [
                    {"message_id": "m1", "text": "已读原文", "images": [{"id": "i1"}, {"id": "i2"}]}
                ],
            },
        },
        {
            "id": "visual-observation",
            "kind": "image_observation",
            "content": {"image_id": "i1", "semantic": True, "text": "实际原图观察"},
        },
    ]
    variants = action_schema(observations)["oneOf"]
    by_kind = {v["properties"]["kind"]["const"]: v for v in variants}
    assert by_kind["read_context"]["properties"]["target_id"]["enum"] == ["m2"]
    assert by_kind["inspect_image"]["properties"]["target_id"]["enum"] == ["i2"]
    selections = by_kind["answer"]["properties"]["evidence"]["items"]["oneOf"]
    assert [
        (v["properties"]["observation_id"]["const"], v["properties"]["message_id"].get("const"))
        for v in selections
    ] == [
        ("read-observation", "m1"),
        ("visual-observation", None),
    ]
    assert set(by_kind["answer"]["properties"]) == {"kind", "evidence"}
    assert set(by_kind["insufficient"]["properties"]) == {"kind"}


def test_nonempty_unread_candidates_require_reading_before_search_or_final():
    variants = action_schema(
        [
            {
                "id": "candidate-observation",
                "kind": "candidate_only",
                "content": {
                    "candidates": [{"message_id": "m1"}],
                },
            }
        ]
    )["oneOf"]
    kinds = [v["properties"]["kind"]["const"] for v in variants]
    assert kinds == ["read_context"]
    assert variants[0]["properties"]["target_id"]["enum"] == ["m1"]


def test_empty_search_allows_reformulation_or_insufficient_without_citations():
    variants = action_schema(
        [
            {
                "id": "empty-search",
                "kind": "candidate_only",
                "content": {"candidates": []},
            }
        ]
    )["oneOf"]
    by_kind = {v["properties"]["kind"]["const"]: v for v in variants}
    assert set(by_kind) == {"search", "insufficient"}
    assert set(by_kind["insufficient"]["properties"]) == {"kind"}


def test_required_image_mode_generates_inspection_before_a_normal_final():
    context = {
        "id": "read",
        "kind": "message_context",
        "content": {
            "messages": [{"message_id": "m1", "images": [{"id": "image-1"}]}],
        },
    }
    variants = action_schema([context], require_image=True)["oneOf"]
    assert len(variants) == 1
    assert variants[0]["properties"]["kind"]["const"] == "inspect_image"
    unavailable = {
        "id": "visual",
        "kind": "image_observation",
        "content": {
            "image_id": "image-1",
            "semantic": False,
        },
    }
    variants = action_schema([context, unavailable], require_image=True)["oneOf"]
    kinds = {v["properties"]["kind"]["const"] for v in variants}
    assert "insufficient" in kinds and "answer" not in kinds


async def test_model_context_excludes_index_text_and_file_processing_state(monkeypatch):
    provider = OllamaProvider(Settings(_env_file=None))
    image = {
        "id": "image-1",
        "filename": "synthetic.png",
        "status": "ready",
        "ocr_text": "secret OCR marker",
        "description": "derived description",
    }
    observations = [
        {
            "id": "read",
            "kind": "message_context",
            "content": {
                "messages": [{"message_id": "m1", "images": [image]}],
            },
        }
    ]

    async def reply(endpoint, payload):
        content = json.loads(payload["messages"][1]["content"])
        assert content["require_image"] is True
        assert content["observations"][0]["content"]["messages"][0]["images"] == [
            {"id": "image-1", "filename": "synthetic.png"},
        ]
        assert "secret OCR marker" not in payload["messages"][1]["content"]
        return {"message": {"content": '{"kind":"inspect_image","target_id":"image-1"}'}}

    monkeypatch.setattr(provider, "_post", reply)
    await provider.plan("核对图中细节", observations, [], require_image=True)
    assert image["ocr_text"] == "secret OCR marker" and image["status"] == "ready"


async def test_empty_vision_response_is_not_a_usable_image_observation(monkeypatch):
    provider = OllamaProvider(Settings(_env_file=None))

    async def empty(endpoint, payload):
        return {"message": {"content": "   "}}

    monkeypatch.setattr(provider, "_post", empty)
    with pytest.raises(ValueError, match="Empty vision response"):
        await provider.vision("synthetic question", b"synthetic-image")


def test_required_image_answer_has_a_required_actual_image_selection():
    observations = [
        {
            "id": "context",
            "kind": "message_context",
            "content": {
                "messages": [
                    {
                        "message_id": "m1",
                        "text": "这是图片附件说明，不能证明像素事实",
                        "images": [{"id": "i1"}],
                    },
                ]
            },
        },
        {
            "id": "visual",
            "kind": "image_observation",
            "content": {
                "image_id": "i1",
                "semantic": True,
                "text": "原图中的圆点为蓝色，位于卡片左端。",
            },
        },
    ]
    answer = next(
        v
        for v in action_schema(observations, require_image=True)["oneOf"]
        if v["properties"]["kind"]["const"] == "answer"
    )
    assert "image_evidence" in answer["required"]
    variants = answer["properties"]["image_evidence"]["oneOf"]
    assert all(v["properties"]["observation_id"]["const"] == "visual" for v in variants)
    assert all(v["properties"]["message_id"]["type"] == "null" for v in variants)
