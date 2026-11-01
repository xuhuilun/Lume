import hashlib
import json

from sqlalchemy import and_, func, or_, select

from .models import Artifact, ImageAsset, Message, ProcessingJob, Revision
from .providers import terms
from .security import DomainError, readable_spaces, require_space


def ingest(session, settings, store, space_id, inputs):
    results = []
    for item in inputs:
        prepared = []
        for image in item.images:
            prepared.append(
                {
                    "filename": image.filename,
                    **(store.decode(image.base64) if image.base64 else {"remote_url": image.url}),
                }
            )
        snapshot = item.model_dump(mode="json", exclude={"images"})
        fingerprint_data = {**snapshot, "images": prepared}
        digest = hashlib.sha256(
            json.dumps(fingerprint_data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        # Serialize a space's imports with its row, including creation of a new source identity.
        from .models import Space

        session.scalar(select(Space).where(Space.id == space_id).with_for_update())
        message = session.scalar(
            select(Message)
            .where(Message.space_id == space_id, Message.source_id == item.source_id)
            .with_for_update()
        )
        if message and message.fingerprint == digest:
            results.append({"id": message.id, "version": message.version, "duplicate": True})
            continue
        if not message:
            message = Message(space_id=space_id, source_id=item.source_id, fingerprint=digest)
            session.add(message)
            session.flush()
        else:
            message.version += 1
            message.fingerprint = digest
        message.active = True
        message.native_index = item.native_index
        session.add(
            Revision(
                message_id=message.id,
                version=message.version,
                content=item.text,
                sent_at=item.sent_at,
                author=item.author,
                reply_to=item.reply_to,
                reply_kind=item.reply_kind,
            )
        )
        session.flush()  # The immutable revision must exist before dependent rows.
        for image in prepared:
            session.add(ImageAsset(message_id=message.id, version=message.version, **image))
        session.add(
            ProcessingJob(
                message_id=message.id, version=message.version, rules_id=settings.rules_id
            )
        )
        results.append({"id": message.id, "version": message.version, "duplicate": False})
    session.flush()
    return results


def current_message(session, user_id, message_id, requested=None):
    message = session.get(Message, message_id)
    if (
        not message
        or not message.active
        or (requested is not None and message.space_id not in requested)
    ):
        raise DomainError("NOT_FOUND", "资料不可用", 404)
    require_space(session, user_id, message.space_id)
    return message


def message_view(session, message):
    revision = session.get(Revision, (message.id, message.version))
    images = session.scalars(
        select(ImageAsset).where(
            ImageAsset.message_id == message.id, ImageAsset.version == message.version
        )
    ).all()
    return {
        "message_id": message.id,
        "version": message.version,
        "source_id": message.source_id,
        "space_id": message.space_id,
        "text": revision.content,
        "author": revision.author,
        "sent_at": revision.sent_at.isoformat(),
        "reply_to": revision.reply_to,
        "images": [
            {
                "id": i.id,
                "filename": i.filename,
                "status": i.status,
                "ocr_text": i.ocr_text,
                "description": i.description,
                "error": i.error,
            }
            for i in images
        ],
    }


def read_context(session, user_id, message_id, requested):
    message = current_message(session, user_id, message_id, requested)
    revision = session.get(Revision, (message.id, message.version))
    ids = {message.id}
    if revision.reply_to:
        parent_key = (
            Message.source_id if revision.reply_kind == "message_id" else Message.native_index
        )
        parent = session.scalar(
            select(Message).where(
                Message.space_id == message.space_id,
                parent_key == revision.reply_to,
                Message.active.is_(True),
            )
        )
        if parent:
            ids.add(parent.id)
    children = session.scalars(
        select(Message)
        .join(
            Revision, and_(Revision.message_id == Message.id, Revision.version == Message.version)
        )
        .where(
            Message.space_id == message.space_id,
            Message.active.is_(True),
            or_(
                and_(Revision.reply_kind == "message_id", Revision.reply_to == message.source_id),
                and_(
                    Revision.reply_kind == "native_index",
                    Message.native_index.is_not(None),
                    Revision.reply_to == message.native_index,
                )
                if message.native_index
                else False,
            ),
        )
        .order_by(Revision.sent_at, Message.id)
        .limit(6)
    ).all()
    ids.update(m.id for m in children)
    members = [session.get(Message, key) for key in ids]
    views = sorted([message_view(session, m) for m in members], key=lambda v: v["sent_at"])
    dependencies = [{"message_id": v["message_id"], "version": v["version"]} for v in views]
    return {"messages": views, "window": "explicit_parent_and_up_to_6_children"}, dependencies


async def search(session_factory, settings, provider, user_id, question, requested):
    vector = await provider.embed(question)
    identity = f"{provider.embedding_identity}:{len(vector)}"
    with session_factory() as session:
        allowed = readable_spaces(session, user_id, requested)
        if not allowed:
            return {"candidates": [], "channels": {"lexical": "ok", "vector": "ok"}}, []
        base = (
            select(Artifact)
            .join(Message)
            .where(
                Message.space_id.in_(allowed),
                Message.active.is_(True),
                Artifact.version == Message.version,
                Artifact.rules_id == settings.rules_id,
            )
        )
        query_terms = terms(question)
        lexical = []
        if query_terms:
            query = func.to_tsquery("simple", " | ".join("'" + t + "'" for t in query_terms))
            lexical = session.scalars(
                base.where(Artifact.search_vector.op("@@")(query))
                .order_by(func.ts_rank_cd(Artifact.search_vector, query).desc(), Artifact.id)
                .limit(settings.retrieval_k)
            ).all()
        dense = session.scalars(
            base.where(Artifact.embedding_space == identity)
            .order_by(Artifact.embedding.cosine_distance(vector), Artifact.id)
            .limit(settings.retrieval_k)
        ).all()
        scores, rows = {}, {}
        for channel, items in [("lexical", lexical), ("vector", dense)]:
            for rank, item in enumerate(items, 1):
                key = (item.message_id, item.version)
                rows[key] = item
                scores.setdefault(key, {"score": 0.0, "ranks": {}})
                scores[key]["score"] += 1 / (settings.rrf_constant + rank)
                scores[key]["ranks"][channel] = rank
        ordered = sorted(scores, key=lambda k: (-scores[k]["score"], k))[: settings.retrieval_k]
        candidates = []
        for key in ordered:
            item = rows[key]
            message = session.get(Message, item.message_id)
            candidates.append(
                {
                    "message_id": message.id,
                    "version": item.version,
                    "source_id": message.source_id,
                    **scores[key],
                }
            )
        dependencies = [
            {"message_id": c["message_id"], "version": c["version"]} for c in candidates
        ]
        return {
            "candidates": candidates,
            "channels": {"lexical": "ok", "vector": "ok"},
        }, dependencies
