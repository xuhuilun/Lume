import asyncio
from datetime import timedelta

from sqlalchemy import and_, func, or_, select

from .leases import maintain_lease
from .models import Artifact, ImageAsset, Message, ProcessingJob, Revision, RuntimeSetting, now
from .providers import terms
from .storage import recognize


class StaleProcessing(Exception):
    pass


class Processor:
    def __init__(self, sessions, settings, provider, store):
        self.sessions, self.settings, self.provider, self.store = (
            sessions,
            settings,
            provider,
            store,
        )

    def claim(self):
        with self.sessions.begin() as session:
            job = session.scalar(
                select(ProcessingJob)
                .where(
                    or_(
                        ProcessingJob.state == "queued",
                        and_(ProcessingJob.state == "running", ProcessingJob.lease_until <= now()),
                    )
                )
                .order_by(ProcessingJob.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not job:
                return None
            if job.attempts >= 3:
                job.state, job.error = "failed", "RECOVERY_EXHAUSTED"
                return (job.id, None)
            job.state, job.epoch = "running", job.epoch + 1
            job.attempts += 1
            job.lease_until = now() + timedelta(seconds=self.settings.lease_seconds)
            return job.id, job.epoch

    def renew(self, job_id, epoch):
        if not self.still_current(job_id, epoch):
            raise StaleProcessing
        with self.sessions.begin() as session:
            job = session.get(ProcessingJob, job_id, with_for_update=True)
            if job.epoch != epoch or job.state != "running" or job.lease_until <= now():
                raise StaleProcessing
            job.lease_until = now() + timedelta(seconds=self.settings.lease_seconds)

    async def run_once(self) -> bool:
        claimed = self.claim()
        if not claimed:
            return False
        job_id, epoch = claimed
        if epoch is None:
            return True
        try:
            async with asyncio.timeout(self.settings.processing_timeout):
                await maintain_lease(
                    self.process(job_id, epoch),
                    min(2, self.settings.lease_seconds / 3),
                    lambda: self.renew(job_id, epoch),
                )
        except Exception as error:
            with self.sessions.begin() as session:
                job = session.get(ProcessingJob, job_id, with_for_update=True)
                if job.epoch == epoch and job.state == "running" and job.lease_until > now():
                    job.state = "superseded" if isinstance(error, StaleProcessing) else "failed"
                    job.error = type(error).__name__[:80]
        return True

    def still_current(self, job_id, epoch):
        with self.sessions() as session:
            job = session.get(ProcessingJob, job_id)
            rule = session.get(RuntimeSetting, "rules_id")
            message = session.get(Message, job.message_id)
            return (
                job.epoch == epoch
                and job.state == "running"
                and job.lease_until > now()
                and message.active
                and message.version == job.version
                and rule
                and rule.value == job.rules_id == self.settings.rules_id
            )

    async def process(self, job_id, epoch):
        if not self.still_current(job_id, epoch):
            with self.sessions.begin() as session:
                old = session.get(ProcessingJob, job_id, with_for_update=True)
                if old.epoch == epoch and old.state == "running" and old.lease_until > now():
                    old.state = "superseded"
            return
        with self.sessions() as session:
            job = session.get(ProcessingJob, job_id)
            message = session.get(Message, job.message_id)
            revision = session.get(Revision, (job.message_id, job.version))
            current_rule = session.get(RuntimeSetting, "rules_id")
            if (
                not message.active
                or message.version != job.version
                or not current_rule
                or current_rule.value != job.rules_id
                or job.rules_id != self.settings.rules_id
            ):
                with self.sessions.begin() as finish:
                    stale = finish.get(ProcessingJob, job_id, with_for_update=True)
                    if (
                        stale.epoch == epoch
                        and stale.state == "running"
                        and stale.lease_until > now()
                    ):
                        stale.state = "superseded"
                return
            content, version, message_id, rules_id = (
                revision.content,
                job.version,
                message.id,
                job.rules_id,
            )
            images = [
                dict(id=i.id, blob=i.blob, remote_url=i.remote_url)
                for i in session.scalars(
                    select(ImageAsset).where(
                        ImageAsset.message_id == message.id, ImageAsset.version == version
                    )
                )
            ]
        updates, fragments = [], [content]
        for image in images:
            update = {"id": image["id"]}
            try:
                if not image["blob"]:
                    update.update(await self.store.download(image["remote_url"]))
                path = self.store.path(update.get("blob", image["blob"]))
                ocr, ocr_error = await recognize(path, self.settings.ocr_lang)
                description = ""
                if not self.still_current(job_id, epoch):
                    return
                if self.settings.provider == "ollama":
                    visual = await self.provider.vision(
                        "概述可见文字、布局和状态，用于之后检索。", path.read_bytes()
                    )
                    description = visual["text"]
                update.update(
                    ocr_text=ocr,
                    description=description,
                    status="ready" if not ocr_error or description else "partial",
                    error=ocr_error,
                )
                fragments.extend([ocr, description])
            except Exception as error:
                update.update(status="failed", error=type(error).__name__[:80])
            updates.append(update)
        text = "\n".join(f for f in fragments if f)[:30_000]
        if not self.still_current(job_id, epoch):
            return
        vector = await self.provider.embed(text)
        with self.sessions.begin() as session:
            job = session.get(ProcessingJob, job_id, with_for_update=True)
            message = session.get(Message, message_id, with_for_update=True)
            rule = session.get(RuntimeSetting, "rules_id", with_for_update=True)
            if job.epoch != epoch or job.state != "running" or job.lease_until <= now():
                return
            if (
                not message.active
                or message.version != version
                or not rule
                or rule.value != rules_id
            ):
                job.state = "superseded"
                return
            for update in updates:
                image = session.get(ImageAsset, update.pop("id"))
                for key, value in update.items():
                    setattr(image, key, value)
            artifact = session.scalar(
                select(Artifact).where(
                    Artifact.message_id == message_id,
                    Artifact.version == version,
                    Artifact.rules_id == rules_id,
                )
            )
            if not artifact:
                artifact = Artifact(message_id=message_id, version=version, rules_id=rules_id)
                session.add(artifact)
            artifact.text, artifact.lexemes = text, " ".join(terms(text))
            artifact.search_vector = func.to_tsvector("simple", artifact.lexemes)
            artifact.embedding = vector
            artifact.embedding_space = f"{self.provider.embedding_identity}:{len(vector)}"
            job.state, job.error = "ready", None
