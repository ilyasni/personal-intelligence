import asyncio

import asyncpg
from pil_observability import configure_logging, get_logger
from pil_storage import RedisClient

from entity_extractor.consumer import run
from entity_extractor.settings import settings


async def main() -> None:
    configure_logging(level=settings.log_level, service="entity-extractor")
    log = get_logger("entity-extractor")

    redis = RedisClient(url=settings.redis_url, password=settings.redis_password or None)
    await redis.ping()
    log.info("redis_connected")

    # asyncpg DSN uses postgresql:// scheme (not postgresql+asyncpg://)
    pg_dsn = settings.postgres_dsn.replace("postgresql+asyncpg://", "postgresql://")
    db_pool = await asyncpg.create_pool(pg_dsn, min_size=2, max_size=8)
    log.info("postgres_connected")

    try:
        await run(redis, db_pool)
    finally:
        await db_pool.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
