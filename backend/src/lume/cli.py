import argparse
import asyncio
import os
from pathlib import Path

import uvicorn
from sqlalchemy import delete, select

from .agent import Runner
from .config import Settings
from .db import database, initialize
from .demo import sample_messages
from .knowledge import ingest
from .models import Artifact, Grant, Message, Principal, ProcessingJob, RuntimeSetting, Space
from .processing import Processor
from .providers import provider_for
from .security import create_user
from .storage import ImageStore


async def work(sessions, settings, limit=None):
    provider, store = provider_for(settings), ImageStore(settings)
    runner, processor = (
        Runner(sessions, settings, provider, store),
        Processor(sessions, settings, provider, store),
    )
    count = 0
    while limit is None or count < limit:
        progressed = await runner.run_once() or await processor.run_once()
        if not progressed:
            if limit is not None:
                break
            await asyncio.sleep(0.5)
        else:
            count += 1


def main():
    parser = argparse.ArgumentParser(description="Lume source-grounded retrieval")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create initial schema and a local administrator")
    init.add_argument("--name", default="admin")
    init.add_argument("--token-file", default=".runtime/admin-token")
    user = commands.add_parser("user", help="Create a local API identity")
    user.add_argument("name")
    user.add_argument("--admin", action="store_true")
    user.add_argument("--token-file", required=True)
    seed = commands.add_parser("seed", help="Import explicitly synthetic demo messages")
    seed.add_argument("--user", default="admin")
    commands.add_parser(
        "reindex", help="Publish current processing rules and rebuild active sources"
    )
    disable = commands.add_parser("disable-user", help="Revoke a local API identity")
    disable.add_argument("name")
    worker = commands.add_parser("worker")
    worker.add_argument("--drain", action="store_true", help="Process queued work, then exit")
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    settings = Settings()
    engine, sessions = database(settings.database_url)
    if args.command in {"init", "user"}:
        if args.command == "init":
            initialize(engine)
        with sessions.begin() as session:
            if session.scalar(select(Principal).where(Principal.name == args.name)):
                raise SystemExit("Identity already exists; refusing to silently replace its token.")
            _, token = create_user(session, args.name, args.command == "init" or args.admin)
            if args.command == "init":
                session.merge(RuntimeSetting(key="rules_id", value=settings.rules_id))
            path = Path(args.token_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                stream.write(token + "\n")
        print(f"Identity created. Token written once to {path}; keep it local.")
    elif args.command == "seed":
        with sessions.begin() as session:
            user = session.scalar(select(Principal).where(Principal.name == args.user))
            if not user:
                raise SystemExit("Create the named identity first.")
            space = session.scalar(select(Space).where(Space.qq_group_id == "synthetic-ops"))
            if not space:
                space = Space(name="演示研发群 · 合成资料", qq_group_id="synthetic-ops")
                session.add(space)
                session.flush()
            session.merge(Grant(user_id=user.id, space_id=space.id, read=True, maintain=True))
            results = ingest(session, settings, ImageStore(settings), space.id, sample_messages())
        print(f"Imported {len(results)} synthetic messages. Run `lume worker --drain`.")
    elif args.command == "disable-user":
        with sessions.begin() as session:
            user = session.scalar(select(Principal).where(Principal.name == args.name))
            if not user:
                raise SystemExit("Identity not found.")
            user.active = False
        print("Identity disabled; subsequent API and model-input checks reject it.")
    elif args.command == "reindex":
        with sessions.begin() as session:
            session.merge(RuntimeSetting(key="rules_id", value=settings.rules_id))
            messages = session.scalars(select(Message).where(Message.active.is_(True))).all()
            for message in messages:
                job = session.scalar(
                    select(ProcessingJob)
                    .where(
                        ProcessingJob.message_id == message.id,
                        ProcessingJob.version == message.version,
                        ProcessingJob.rules_id == settings.rules_id,
                    )
                    .with_for_update()
                )
                if not job:
                    session.add(
                        ProcessingJob(
                            message_id=message.id,
                            version=message.version,
                            rules_id=settings.rules_id,
                        )
                    )
                else:
                    job.epoch += 1
                    job.state, job.attempts, job.lease_until, job.error = "queued", 0, None, None
                session.execute(
                    delete(Artifact).where(
                        Artifact.message_id == message.id,
                        Artifact.version == message.version,
                        Artifact.rules_id == settings.rules_id,
                    )
                )
        print(f"Queued {len(messages)} active sources with the configured rules. Restart services.")
    elif args.command == "worker":
        asyncio.run(work(sessions, settings, 1000 if args.drain else None))
    else:
        # The QQ callback URL contains a registration credential: do not emit access paths.
        uvicorn.run("lume.api:app", host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
