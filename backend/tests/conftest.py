import os
import uuid
from types import SimpleNamespace

import httpx
import pytest
from lume.agent import Runner
from lume.api import create_app
from lume.config import Settings
from lume.models import Base, Grant, RuntimeSetting, Space
from lume.processing import Processor
from lume.providers import DemoProvider
from lume.security import create_user
from lume.storage import ImageStore
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def system(tmp_path):
    url = os.environ.get("LUME_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set LUME_TEST_DATABASE_URL to an isolated PostgreSQL/pgvector test database")
    schema = "test_" + uuid.uuid4().hex
    admin_engine = create_engine(url)
    with admin_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema},public"})
    Base.metadata.create_all(engine, checkfirst=False)
    sessions = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        database_url=url,
        data_dir=tmp_path,
        qq_app_id="test-app",
        qq_secret="synthetic-test-secret",
        qq_webhook_token="test-registration-key-" + "x" * 32,
    )
    with sessions.begin() as session:
        alice, alice_token = create_user(session, "alice", admin=True)
        bob, bob_token = create_user(session, "bob")
        a, b = Space(name="A", qq_group_id="group-A", ingest_enabled=True), Space(name="B")
        session.add_all([a, b])
        session.flush()
        session.add_all(
            [
                Grant(user_id=alice.id, space_id=a.id, read=True, maintain=True),
                Grant(user_id=bob.id, space_id=b.id, read=True, maintain=True),
                RuntimeSetting(key="rules_id", value=settings.rules_id),
            ]
        )
    provider, store = DemoProvider(), ImageStore(settings)
    app = create_app(settings, sessions)
    value = SimpleNamespace(
        settings=settings,
        sessions=sessions,
        provider=provider,
        store=store,
        alice=alice.id,
        bob=bob.id,
        a=a.id,
        b=b.id,
        app=app,
        alice_headers={"Authorization": "Bearer " + alice_token},
        bob_headers={"Authorization": "Bearer " + bob_token},
    )
    value.processor = Processor(sessions, settings, provider, store)
    value.runner = Runner(sessions, settings, provider, store)
    yield value
    engine.dispose()
    with admin_engine.begin() as connection:
        connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    admin_engine.dispose()


@pytest.fixture
async def client(system):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=system.app),
        base_url="http://test",
        headers=system.alice_headers,
    ) as client:
        yield client


def packet(source_id="one", text="E_CONN_42 pool_size adjusted to 20", **extra):
    return {"source_id": source_id, "text": text, "sent_at": "2026-11-01T08:00:00Z", **extra}


async def prepare(client, system, messages=None):
    response = await client.post(
        f"/api/spaces/{system.a}/imports", json={"messages": messages or [packet()]}
    )
    assert response.status_code == 202, response.text
    while await system.processor.run_once():
        pass
    return response.json()["messages"]


async def ask(client, system, question="E_CONN_42如何处理", **extra):
    response = await client.post(
        "/api/tasks",
        json={
            "question": question,
            "space_ids": [system.a],
            **extra,
        },
    )
    assert response.status_code == 202, response.text
    await system.runner.run_once()
    status = (await client.get("/api/tasks/" + response.json()["id"])).json()
    return status
