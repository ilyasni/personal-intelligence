import asyncio

import asyncpg
from pil_observability import configure_logging, get_logger
from pil_storage import RedisClient, S3Client

from chat_summarizer.consumer import run
from chat_summarizer.llm import ChatSummaryEngine
from chat_summarizer.settings import settings


async def main() -> None:
    configure_logging(level=settings.log_level, service="chat-summarizer")
    log = get_logger("chat-summarizer")

    redis = RedisClient(url=settings.redis_url, password=settings.redis_password or None)
    await redis.ping()
    log.info("redis_connected")

    s3 = S3Client(
        endpoint_url=settings.s3_endpoint_url,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
        region=settings.s3_region,
        bucket_raw=settings.s3_bucket_raw,
        bucket_media=settings.s3_bucket_media,
    )

    pg_dsn = settings.postgres_dsn.replace("postgresql+asyncpg://", "postgresql://")
    db_pool = await asyncpg.create_pool(pg_dsn, min_size=2, max_size=8)
    log.info("postgres_connected")
    summary_engine = ChatSummaryEngine(settings.summarizer_llm_mode)
    log.info("summary_engine_ready", mode=summary_engine.mode)

    try:
        await run(redis, s3, db_pool, summary_engine)
    finally:
        await summary_engine.close()
        await db_pool.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
