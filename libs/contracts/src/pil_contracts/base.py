from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from ulid import ULID


def _ulid() -> str:
    return str(ULID())


def _now() -> datetime:
    return datetime.now(UTC)


class BaseEvent(BaseModel):
    """Базовый класс для всех событий на шине Redis Streams."""

    event_id: str = Field(default_factory=_ulid)
    schema_version: int = 1
    occurred_at: datetime = Field(default_factory=_now)
    trace_id: str | None = None
    backfill: bool = False

    model_config = {"frozen": True}


class BaseCommand(BaseModel):
    """Базовый класс для системных команд."""

    command_id: str = Field(default_factory=_ulid)
    schema_version: int = 1
    issued_at: datetime = Field(default_factory=_now)
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}
