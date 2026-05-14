import asyncio

import asyncpg
from pil_observability import configure_logging, get_logger
from pil_storage import RedisClient

from persona_builder.consumer import run
from persona_builder.settings import settings


async def main() -> None:
    configure_logging(level=settings.log_level, service="persona-builder")
    log = get_logger("persona-builder")

    redis = RedisClient(url=settings.redis_url, password=settings.redis_password or None)
    await redis.ping()
    log.info("redis_connected")

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
