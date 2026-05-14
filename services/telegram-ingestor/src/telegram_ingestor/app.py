"""aiogram polling setup + healthz HTTP endpoint."""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import FastAPI

from pil_observability import get_logger
from pil_storage import RedisClient, S3Client

from telegram_ingestor.handlers import router
from telegram_ingestor.pil_aiohttp_session import PilAiohttpSession
from telegram_ingestor.settings import settings

log = get_logger(__name__)


async def create_app() -> tuple[FastAPI, Bot, Dispatcher]:
    session = PilAiohttpSession(
        proxy=settings.tg_proxy_url or None,
        timeout=settings.tg_api_timeout_seconds,
    )
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    redis = RedisClient(url=settings.redis_url, password=settings.redis_password or None)
    s3 = S3Client(
        endpoint_url=settings.s3_endpoint_url,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
        region=settings.s3_region,
        bucket_raw=settings.s3_bucket_raw,
        bucket_media=settings.s3_bucket_media,
    )
    dp["redis"] = redis
    dp["s3"] = s3

    # delete_webhook не вызываем здесь: см. __main__ (liveness: uvicorn /healthz до медленного Telegram)

    # Healthz endpoint — отдельный FastAPI, слушает на порту :8080
    app = FastAPI(title="PIL telegram-ingestor", docs_url=None)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    return app, bot, dp


async def ensure_polling_mode(bot: Bot) -> None:
    """Снять webhook перед long polling (дорогой вызов через прокси — не блокирует поднятие /healthz)."""
    await bot.delete_webhook(drop_pending_updates=False)
    log.info("webhook deleted, switching to polling")
