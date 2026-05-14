from __future__ import annotations

import asyncio
import signal
from contextlib import suppress

import asyncpg

from ai_orchestrator.consumer import run
from ai_orchestrator.llm import AnalysisRouter
from ai_orchestrator.settings import settings
from pil_observability import configure_logging
from pil_storage import RedisClient


async def main() -> None:
    configure_logging(level=settings.log_level, service="ai-orchestrator")
    redis = RedisClient(url=settings.redis_url, password=settings.redis_password or None)
    pg_dsn = settings.postgres_dsn.replace("postgresql+asyncpg://", "postgresql://")
    db_pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=6)
    router = AnalysisRouter()
    stop_event = asyncio.Event()

    consumer_task = asyncio.create_task(run(redis, db_pool, router))
    stop_waiter = asyncio.create_task(stop_event.wait())

    def _stop() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for signame in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signame, None)
        if sig is None:
            continue
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, _stop)

    try:
        done, _ = await asyncio.wait(
            {consumer_task, stop_waiter},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if consumer_task in done:
            await consumer_task
    finally:
        stop_waiter.cancel()
        consumer_task.cancel()
        await asyncio.gather(stop_waiter, consumer_task, return_exceptions=True)
        await router.close()
        await db_pool.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
