import hashlib
import secrets
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from .knowledge import ingest
from .models import QQDelivery, Space
from .schemas import ImageInput, MessageInput
from .security import DomainError


def key_for(secret: str):
    data = secret.encode()
    if not data:
        raise DomainError("QQ_NOT_CONFIGURED", "QQ接入尚未配置", 503)
    seed = (data * ((32 + len(data) - 1) // len(data)))[:32]
    return Ed25519PrivateKey.from_private_bytes(seed)


def verify_signature(secret, timestamp, body, signature, window=300, clock=None):
    try:
        if abs((time.time() if clock is None else clock) - int(timestamp)) > window:
            raise ValueError
        key_for(secret).public_key().verify(bytes.fromhex(signature), timestamp.encode() + body)
    except (ValueError, TypeError, InvalidSignature):
        raise DomainError("QQ_SIGNATURE_INVALID", "回调签名或时间窗无效", 401) from None


def authorize_path(settings, token, app_id):
    if not settings.qq_app_id or not settings.qq_secret or len(settings.qq_webhook_token) < 32:
        raise DomainError("QQ_NOT_CONFIGURED", "QQ接入尚未配置", 503)
    if not secrets.compare_digest(token, settings.qq_webhook_token) or not secrets.compare_digest(
        app_id, settings.qq_app_id
    ):
        raise DomainError("NOT_FOUND", "对象不可用", 404)


def normalize(payload):
    data = payload["d"]
    if not isinstance(data, dict):
        raise TypeError("dispatch data must be an object")
    extensions = {}
    for entry in data.get("message_scene", {}).get("ext", []):
        if isinstance(entry, str) and "=" in entry:
            key, value = entry.split("=", 1)
            if key in {"msg_idx", "ref_msg_idx"}:
                extensions[key] = value
    author = data.get("author", {})
    return MessageInput(
        source_id=data["id"],
        text=data.get("content", ""),
        sent_at=data["timestamp"],
        author=str(author.get("member_openid", author.get("id", ""))),
        native_index=extensions.get("msg_idx"),
        reply_to=extensions.get("ref_msg_idx"),
        reply_kind="native_index",
        images=[
            ImageInput(filename=a.get("filename", "image"), url=a["url"])
            for a in data.get("attachments", [])
            if a.get("content_type", "").startswith("image/")
        ],
    )


def handle_event(session, settings, store, payload):
    ack = {"op": 12, "d": 0}
    if payload.get("op") != 0 or payload.get("t") not in {
        "GROUP_AT_MESSAGE_CREATE",
        "GROUP_MESSAGE_CREATE",
    }:
        return ack
    try:
        group = payload["d"]["group_openid"]
        message = normalize(payload)
    except (KeyError, TypeError, AttributeError, ValidationError):
        raise DomainError("QQ_PAYLOAD_INVALID", "群消息字段无效", 422) from None
    space = session.scalar(
        select(Space).where(Space.qq_group_id == group, Space.ingest_enabled.is_(True))
    )
    if not space:
        return ack  # Receiving an event never creates a public space or a permission grant.
    delivery_id = str(
        payload.get("id")
        or hashlib.sha256((str(payload["t"]) + message.source_id).encode()).hexdigest()
    )
    if len(delivery_id) > 300:
        raise DomainError("QQ_PAYLOAD_INVALID", "事件身份过长", 422)
    inserted = session.scalar(
        insert(QQDelivery).values(id=delivery_id).on_conflict_do_nothing().returning(QQDelivery.id)
    )
    if inserted:
        ingest(session, settings, store, space.id, [message])
    return ack
