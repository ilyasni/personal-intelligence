import asyncio

from pil_observability import configure_logging

from maintenance.service import run
from maintenance.settings import settings


async def main() -> None:
    configure_logging(level=settings.log_level, service="maintenance")
    await run()


if __name__ == "__main__":
    asyncio.run(main())
