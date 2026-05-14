"""aiogram handlers для Business Bot update types."""

import json
from datetime import datetime, timezone
from typing import Any

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
    log.info(
        "business_message",
        chat_id=message.chat.id,
        message_id=message.message_id,
        from_user=message.from_user.id if message.from_user else None,
    )
    # Сохраняем raw в S3
    raw_key = _s3_key(message.chat.id, message.message_id, message.date)
    if s3.is_configured:
        try:
            await s3.put_raw(raw_key, _serialize_message_json(message))
        except Exception:
            log.warning("s3_put_failed", key=raw_key, exc_info=True)
            raw_key = None  # не блокируем pipeline если S3 недоступен
    else:
        raw_key = None

    chat_type = message.chat.type if isinstance(message.chat.type, str) else (message.chat.type.value if message.chat.type else "private")

    contract = TelegramMessageEvent(
        tg_chat_id=message.chat.id,
        tg_message_id=message.message_id,
        tg_sender_id=message.from_user.id if message.from_user else None,
        tg_sender_username=message.from_user.username if message.from_user else None,
        tg_sender_name=message.from_user.full_name if message.from_user else None,
        chat_title=message.chat.title or message.chat.full_name,
        chat_type=chat_type,  # type: ignore[arg-type]
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
        edit_date=message.edit_date,
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
    ts = dt or datetime.now(timezone.utc)
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


def _serialize_message_json(message: Message) -> bytes:
    """Serialize aiogram Message safely even when nested Default values appear."""
    payload: dict[str, Any] = message.model_dump(mode="python")
    return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
