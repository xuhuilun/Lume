import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid() -> str:
    return uuid.uuid4().hex


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class RuntimeSetting(Base):
    __tablename__ = "runtime_setting"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(String(500))


class Principal(Base):
    __tablename__ = "principal"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Space(Base):
    __tablename__ = "source_space"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    qq_group_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    ingest_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class Grant(Base):
    __tablename__ = "scope_grant"
    user_id: Mapped[str] = mapped_column(ForeignKey("principal.id"), primary_key=True)
    space_id: Mapped[str] = mapped_column(ForeignKey("source_space.id"), primary_key=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    maintain: Mapped[bool] = mapped_column(Boolean, default=False)


class Message(Base):
    __tablename__ = "source_message"
    __table_args__ = (UniqueConstraint("space_id", "source_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    space_id: Mapped[str] = mapped_column(ForeignKey("source_space.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(300))
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    native_index: Mapped[str | None] = mapped_column(String(300))


class Revision(Base):
    __tablename__ = "message_revision"
    message_id: Mapped[str] = mapped_column(ForeignKey("source_message.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    author: Mapped[str] = mapped_column(String(200), default="")
    reply_to: Mapped[str | None] = mapped_column(String(300))
    reply_kind: Mapped[str] = mapped_column(String(30), default="message_id")


class ImageAsset(Base):
    __tablename__ = "image_asset"
    __table_args__ = (
        ForeignKeyConstraint(
            ["message_id", "version"], ["message_revision.message_id", "message_revision.version"]
        ),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    message_id: Mapped[str] = mapped_column(ForeignKey("source_message.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(200))
    blob: Mapped[str | None] = mapped_column(String(80))
    digest: Mapped[str | None] = mapped_column(String(64))
    mime: Mapped[str | None] = mapped_column(String(80))
    remote_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(String(80))


class Artifact(Base):
    __tablename__ = "derived_artifact"
    __table_args__ = (
        UniqueConstraint("message_id", "version", "rules_id"),
        ForeignKeyConstraint(
            ["message_id", "version"], ["message_revision.message_id", "message_revision.version"]
        ),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    message_id: Mapped[str] = mapped_column(ForeignKey("source_message.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    rules_id: Mapped[str] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text)
    lexemes: Mapped[str] = mapped_column(Text)
    search_vector: Mapped[object] = mapped_column(TSVECTOR)
    embedding: Mapped[list[float]] = mapped_column(Vector())
    embedding_space: Mapped[str] = mapped_column(String(500))


class ProcessingJob(Base):
    __tablename__ = "processing_job"
    __table_args__ = (
        UniqueConstraint("message_id", "version", "rules_id"),
        ForeignKeyConstraint(
            ["message_id", "version"], ["message_revision.message_id", "message_revision.version"]
        ),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    message_id: Mapped[str] = mapped_column(ForeignKey("source_message.id"))
    version: Mapped[int] = mapped_column(Integer)
    rules_id: Mapped[str] = mapped_column(String(500))
    state: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    epoch: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(80))


class Task(Base):
    __tablename__ = "qa_task"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("principal.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    requested_scope: Mapped[list[str]] = mapped_column(JSONB)
    history_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    config: Mapped[dict] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    epoch: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recoveries: Mapped[int] = mapped_column(Integer, default=0)
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    image_calls: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    error: Mapped[str | None] = mapped_column(String(80))


class ActionRecord(Base):
    __tablename__ = "task_action"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("qa_task.id"), index=True)
    epoch: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(50))
    state: Mapped[str] = mapped_column(String(30), default="reserved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Observation(Base):
    __tablename__ = "tool_observation"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("qa_task.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    content: Mapped[dict] = mapped_column(JSONB)
    dependencies: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Answer(Base):
    __tablename__ = "answer"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("qa_task.id"), unique=True)
    text: Mapped[str] = mapped_column(Text)
    citation_ids: Mapped[list[str]] = mapped_column(JSONB)
    dependencies: Mapped[list[dict]] = mapped_column(JSONB)


class TaskEvent(Base):
    __tablename__ = "task_event"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("qa_task.id"), index=True)
    kind: Mapped[str] = mapped_column(String(60))
    elapsed: Mapped[float | None] = mapped_column(Float)


class QQDelivery(Base):
    __tablename__ = "qq_delivery"
    id: Mapped[str] = mapped_column(String(300), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
