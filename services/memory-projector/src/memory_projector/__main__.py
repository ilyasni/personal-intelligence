from __future__ import annotations

import asyncio
import signal
from contextlib import suppress

import asyncpg

from memory_projector.consumer import build_neo4j_driver, run
from memory_projector.settings import settings
from pil_observability import configure_logging
from pil_storage import RedisClient, S3Client


async def main() -> None:
    configure_logging(level=settings.log_level, service="memory-projector")
    redis = RedisClient(url=settings.redis_url, password=settings.redis_password or None)
    s3 = S3Client(
        endpoint_url=settings.s3_endpoint_url,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
        region=settings.s3_region,
        bucket_raw=settings.s3_bucket_raw,
        bucket_media=settings.s3_bucket_media,
    )
    pg_dsn = settings.postgres_dsn.replace("postgresql+asyncpg://", "postgresql://")
    db_pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=6)
    neo4j_driver = build_neo4j_driver()
    if neo4j_driver is not None:
        await neo4j_driver.verify_connectivity()

    stop_event = asyncio.Event()
    consumer_task = asyncio.create_task(run(redis, s3, db_pool, neo4j_driver))
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
        if neo4j_driver is not None:
            await neo4j_driver.close()
        await db_pool.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
