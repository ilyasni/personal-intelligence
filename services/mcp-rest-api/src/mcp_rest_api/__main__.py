from __future__ import annotations

import uvicorn

from mcp_rest_api.app import app
from mcp_rest_api.settings import settings
from pil_observability import configure_logging


def main() -> None:
    configure_logging(level=settings.log_level, service="mcp-rest-api")
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
