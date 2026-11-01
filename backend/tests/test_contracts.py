import math

import pytest
from lume.models import Observation, Task
from lume.providers import OllamaProvider
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
