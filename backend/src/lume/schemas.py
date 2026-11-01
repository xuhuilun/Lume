from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ImageInput(Input):
    filename: str = Field(min_length=1, max_length=200)
    base64: str | None = Field(default=None, max_length=5_400_000)
    url: str | None = Field(default=None, max_length=3000)

    @model_validator(mode="after")
    def exactly_one(self):
        if bool(self.base64) == bool(self.url):
            raise ValueError("Exactly one image source is required")
        return self


class MessageInput(Input):
    source_id: str = Field(min_length=1, max_length=300)
    text: str = Field(max_length=30_000)
    sent_at: datetime
    author: str = Field(default="", max_length=200)
    reply_to: str | None = Field(default=None, max_length=300)
    reply_kind: Literal["message_id", "native_index"] = "message_id"
    native_index: str | None = Field(default=None, max_length=300)
    images: list[ImageInput] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def has_timezone(self):
        if self.sent_at.tzinfo is None:
            raise ValueError("sent_at must include a timezone")
        if not self.text and not self.images:
            raise ValueError("Message must contain text or an image")
        return self


class ImportInput(Input):
    messages: list[MessageInput] = Field(min_length=1, max_length=100)


class SpaceInput(Input):
    name: str = Field(min_length=1, max_length=120)
    qq_group_id: str | None = Field(default=None, min_length=1, max_length=200)
    ingest_enabled: bool = False


class GrantInput(Input):
    read: bool
    maintain: bool


class TaskInput(Input):
    question: str = Field(min_length=1, max_length=2000)
    space_ids: list[str] = Field(min_length=1, max_length=30)
    history_ids: list[str] = Field(default_factory=list, max_length=5)


class AgentAction(Input):
    kind: Literal["search", "read_context", "inspect_image", "final"]
    query: str | None = Field(default=None, max_length=2000)
    target_id: str | None = Field(default=None, max_length=100)
    answer: str | None = Field(default=None, max_length=12_000)
    citation_ids: list[str] = Field(default_factory=list, max_length=10)
    insufficient: bool = False

    @model_validator(mode="after")
    def required_fields(self):
        if self.kind == "search" and not self.query:
            raise ValueError("search requires query")
        if self.kind in {"read_context", "inspect_image"} and not self.target_id:
            raise ValueError("read requires target_id")
        if self.kind == "final" and not self.answer:
            raise ValueError("final requires answer")
        return self
