"""aiogram handlers for Business Bot update types."""

import json
from datetime import UTC, datetime
from typing import Any, Literal, cast

from aiogram import Router
from aiogram.types import BusinessConnection, BusinessMessagesDeleted, Message

from pil_contracts import (
    TelegramBusinessConnectionEvent,
    TelegramMessageDeletedEvent,
    TelegramMessageEditedEvent,
    TelegramMessageEvent,
)
from pil_observability import get_logger
from pil_storage import RedisClient, S3Client

router = Router(name="business")
log = get_logger(__name__)

ChatType = Literal["private", "group", "supergroup", "channel"]


# ── business_connection ───────────────────────────────────────────────────────

@router.business_connection()
async def on_business_connection(
    event: BusinessConnection,
    redis: RedisClient,
) -> None:
    log.info(
        "business_connection",
        connection_id=event.id,
        user_id=event.user.id,
        is_enabled=event.is_enabled,
    )
    contract = TelegramBusinessConnectionEvent(
        connection_id=event.id,
        tg_user_id=event.user.id,
        is_enabled=event.is_enabled,
    )
    await redis.xadd(contract.stream, {"data": contract.model_dump_json()})


# ── business_message ──────────────────────────────────────────────────────────

@router.business_message()
async def on_business_message(
    message: Message,
    redis: RedisClient,
    s3: S3Client,
) -> None:
    storage_key = _s3_key(message.chat.id, message.message_id, message.date)
    raw_key: str | None = storage_key
    log.info(
        "business_message",
        chat_id=message.chat.id,
        message_id=message.message_id,
        from_user=message.from_user.id if message.from_user else None,
    )
    # Persist the raw Telegram payload in S3 when storage is configured.
    if s3.is_configured:
        try:
            await s3.put_raw(storage_key, _serialize_message_json(message))
        except Exception:
            log.warning("s3_put_failed", key=raw_key, exc_info=True)
            raw_key = None  # Do not block the pipeline when object storage is unavailable.
    else:
        raw_key = None

    chat_type = _normalize_chat_type(message.chat.type)

    contract = TelegramMessageEvent(
        tg_chat_id=message.chat.id,
        tg_message_id=message.message_id,
        tg_sender_id=message.from_user.id if message.from_user else None,
        tg_sender_username=message.from_user.username if message.from_user else None,
        tg_sender_name=message.from_user.full_name if message.from_user else None,
        chat_title=message.chat.title or message.chat.full_name,
        chat_type=chat_type,
        text=message.text or message.caption,
        media_type=_media_type(message),
        reply_to_message_id=message.reply_to_message.message_id if message.reply_to_message else None,
        via_business_bot=True,
        is_forwarded=message.forward_origin is not None,
        tg_date=message.date,
        raw_s3_key=raw_key,
    )
    await redis.xadd(contract.stream, {"data": contract.model_dump_json()})


# ── edited_business_message ───────────────────────────────────────────────────

@router.edited_business_message()
async def on_edited_business_message(
    message: Message,
    redis: RedisClient,
) -> None:
    contract = TelegramMessageEditedEvent(
        tg_chat_id=message.chat.id,
        tg_message_id=message.message_id,
        edit_date=_normalize_edit_date(message.edit_date),
        new_text=message.text or message.caption,
    )
    await redis.xadd(contract.stream, {"data": contract.model_dump_json()})


# ── deleted_business_messages ─────────────────────────────────────────────────

@router.deleted_business_messages()
async def on_deleted_business_messages(
    event: BusinessMessagesDeleted,
    redis: RedisClient,
) -> None:
    contract = TelegramMessageDeletedEvent(
        tg_chat_id=event.chat.id,
        tg_message_ids=list(event.message_ids),
    )
    await redis.xadd(contract.stream, {"data": contract.model_dump_json()})


# ── helpers ───────────────────────────────────────────────────────────────────

def _s3_key(chat_id: int, message_id: int, dt: datetime | None) -> str:
    ts = dt or datetime.now(UTC)
    return f"{ts.year}/{ts.month:02d}/{ts.day:02d}/{chat_id}/{message_id}.json"


def _media_type(message: Message) -> str | None:
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.voice:
        return "voice"
    if message.audio:
        return "audio"
    if message.document:
        return "document"
    if message.sticker:
        return "sticker"
    if message.video_note:
        return "video_note"
    return None


def _normalize_chat_type(value: object) -> ChatType:
    if isinstance(value, str) and value in {"private", "group", "supergroup", "channel"}:
        return cast("ChatType", value)
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str) and enum_value in {"private", "group", "supergroup", "channel"}:
        return cast("ChatType", enum_value)
    return "private"


def _normalize_edit_date(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC)
    return None


def _serialize_message_json(message: Message) -> bytes:
    """Serialize aiogram Message safely even when nested Default values appear."""
    payload: dict[str, Any] = message.model_dump(mode="python")
    return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
