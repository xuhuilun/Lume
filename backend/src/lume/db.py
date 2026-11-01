from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .models import Base


def database(url: str):
    engine = create_engine(url, pool_pre_ping=True)
    return engine, sessionmaker(engine, expire_on_commit=False)


def initialize(engine):
    # Initial schema only: never silently migrate or delete an existing installation.
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(
            text("CREATE TABLE IF NOT EXISTS lume_schema (version integer PRIMARY KEY)")
        )
        versions = connection.execute(text("SELECT version FROM lume_schema")).scalars().all()
        if versions and versions != [1]:
            raise RuntimeError("Unsupported database schema; explicit migration required")
        Base.metadata.create_all(connection)
        if not versions:
            connection.execute(text("INSERT INTO lume_schema VALUES (1)"))
