import asyncio

import uvicorn

from pil_observability import configure_logging, get_logger

from telegram_ingestor.app import create_app, ensure_polling_mode
from telegram_ingestor.settings import settings

log = get_logger(__name__)


async def main() -> None:
    configure_logging(level=settings.log_level, service="telegram-ingestor")
    log.info("telegram-ingestor starting", mode="polling", port=settings.port)

    app, bot, dp = await create_app()

    # Uvicorn и Telegram параллельно: /healthz доступен до завершения delete_webhook (Docker liveness).
    async def run_polling() -> None:
        await ensure_polling_mode(bot)
        await dp.start_polling(
            bot,
            allowed_updates=[
                "business_connection",
                "business_message",
                "edited_business_message",
                "deleted_business_messages",
            ],
            handle_signals=False,
        )

    async def run_healthz() -> None:
        config = uvicorn.Config(
            app, host="0.0.0.0", port=settings.port,
            log_level=settings.log_level.lower(),
        )
        server = uvicorn.Server(config)
        await server.serve()

    await asyncio.gather(run_polling(), run_healthz())


if __name__ == "__main__":
    asyncio.run(main())
