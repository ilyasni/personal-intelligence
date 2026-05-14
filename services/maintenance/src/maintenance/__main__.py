import asyncio

from maintenance.service import run
from maintenance.settings import settings
from pil_observability import configure_logging


async def main() -> None:
    configure_logging(level=settings.log_level, service="maintenance")
    await run()


if __name__ == "__main__":
    asyncio.run(main())
