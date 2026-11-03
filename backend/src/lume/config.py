from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LUME_", env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://lume:lume@127.0.0.1:5432/lume"
    data_dir: Path = Path("data")
    provider: Literal["demo", "ollama"] = "demo"
    ollama_url: str = "http://127.0.0.1:11434"
    embed_model: str = "embeddinggemma"
    chat_model: str = "qwen3:4b"
    vision_model: str = "qwen2.5vl:3b"
    model_revision: str = "local-v1"
    ocr_lang: str = "eng"
    qq_app_id: str = ""
    qq_secret: str = ""
    qq_webhook_token: str = ""
    qq_timestamp_window: int = 300
    attachment_hosts: tuple[str, ...] = ("multimedia.nt.qq.com.cn",)
    max_image_bytes: int = 4_000_000
    max_image_pixels: int = 12_000_000
    max_request_bytes: int = 12_000_000
    max_model_calls: int = 12
    max_tool_calls: int = 8
    max_image_calls: int = 2
    max_context_chars: int = 32_000
    task_timeout: int = 90
    processing_timeout: int = 90
    lease_seconds: int = 15
    max_recoveries: int = 2
    retrieval_k: int = 12
    rrf_constant: int = 60

    @model_validator(mode="after")
    def bounded(self):
        for field in (
            "max_model_calls",
            "max_tool_calls",
            "max_image_calls",
            "max_context_chars",
            "task_timeout",
            "processing_timeout",
            "lease_seconds",
            "retrieval_k",
            "rrf_constant",
            "qq_timestamp_window",
            "max_image_bytes",
            "max_request_bytes",
        ):
            if getattr(self, field) <= 0:
                raise ValueError(f"{field} must be positive")
        return self

    @property
    def rules_id(self) -> str:
        protocol = "v2" if self.provider == "ollama" else "v1"
        return (
            f"{protocol}:{self.provider}:{self.embed_model}:{self.chat_model}:{self.vision_model}:"
            f"{self.model_revision}:ocr={self.ocr_lang}"
        )
