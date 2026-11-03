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
                "messages": [{"message_id": "m1", "images": [{"id": "i1"}, {"id": "i2"}]}],
            },
        },
        {"id": "visual-observation", "kind": "image_observation", "content": {"image_id": "i1"}},
    ]
    variants = action_schema(observations)["oneOf"]
    by_kind = {v["properties"]["kind"]["const"]: v for v in variants}
    assert by_kind["read_context"]["properties"]["target_id"]["enum"] == ["m2"]
    assert by_kind["inspect_image"]["properties"]["target_id"]["enum"] == ["i2"]
    for variant in variants:
        if variant["properties"]["kind"]["const"] == "final":
            assert variant["properties"]["citation_ids"]["items"]["enum"] == [
                "read-observation",
                "visual-observation",
            ]


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
    assert set(by_kind) == {"search", "final"}
    final = by_kind["final"]["properties"]
    assert final["insufficient"]["const"] is True
    assert final["citation_ids"]["maxItems"] == 0
