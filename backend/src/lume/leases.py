import asyncio
from contextlib import suppress


async def maintain_lease(coroutine, interval, renew):
    """Renew only a live ownership claim; cancellation cannot undo external computation."""
    work = asyncio.create_task(coroutine)
    try:
        while True:
            done, _ = await asyncio.wait({work}, timeout=interval)
            if done:
                return await work
            renew()
    finally:
        if not work.done():
            work.cancel()
            with suppress(asyncio.CancelledError):
                await work
