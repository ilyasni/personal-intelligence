"""Redis Streams consumer: telegram messages -> interaction summaries."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import asyncpg
import structlog
from pil_contracts import (
    InteractionUpdatedEvent,
    STREAM_DLQ_SUMMARIZER,
    STREAM_INTERACTION_UPDATED,
    TelegramMessageEditedEvent,
    TelegramMessageEvent,
)
from pil_storage import RedisClient, S3Client

from chat_summarizer.llm import ChatSummaryEngine, LlmWindowMessage
from chat_summarizer.settings import settings
from chat_summarizer.windowing import needs_rollover

log = structlog.get_logger("chat-summarizer.consumer")

_CONSUMER_NAME = "chat-summarizer"


@dataclass
class WindowMessage:
    tg_message_id: int
    tg_sender_id: int | None
    tg_sender_name: str | None
    chat_type: str
    chat_title: str | None
    text: str
    occurred_at: str


async def _is_processed(conn: asyncpg.Connection, event_id: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM processed_event WHERE consumer_name = $1 AND event_id = $2 LIMIT 1",
        _CONSUMER_NAME,
        event_id,
    )
    return row is not None


async def _mark_processed(conn: asyncpg.Connection, event_id: str) -> None:
    await conn.execute(
        "INSERT INTO processed_event (consumer_name, event_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        _CONSUMER_NAME,
        event_id,
    )


async def _ensure_groups(redis: RedisClient) -> None:
    for stream in (settings.stream_message, settings.stream_message_edited):
        try:
            await redis.r.xgroup_create(stream, settings.consumer_group, id="$", mkstream=True)
        except Exception:
            pass


async def _process_stream(
    stream: str,
    msg_id: str,
    fields: dict,
    redis: RedisClient,
    s3: S3Client,
    db_pool: asyncpg.Pool,
    summary_engine: ChatSummaryEngine,
) -> None:
    raw = fields.get("data", "{}")
    if stream == settings.stream_message:
        event = TelegramMessageEvent.model_validate_json(raw)
        await _handle_message(event, redis, s3, db_pool, summary_engine)
        return
    if stream == settings.stream_message_edited:
        event = TelegramMessageEditedEvent.model_validate_json(raw)
        await _handle_edited_message(event, redis, db_pool)
        return
    log.warning("unknown_stream", stream=stream, msg_id=msg_id)


async def _handle_message(
    event: TelegramMessageEvent,
    redis: RedisClient,
    s3: S3Client,
    db_pool: asyncpg.Pool,
    summary_engine: ChatSummaryEngine,
) -> None:
    text = (event.text or "").strip()
    if not text:
        return

    occurred_at = (event.tg_date or event.occurred_at).astimezone(UTC)
    payload = WindowMessage(
        tg_message_id=event.tg_message_id,
        tg_sender_id=event.tg_sender_id,
        tg_sender_name=event.tg_sender_name,
        chat_type=event.chat_type,
        chat_title=event.chat_title,
        text=text,
        occurred_at=occurred_at.isoformat(),
    )
    key = _window_key(event.tg_chat_id)

    async with db_pool.acquire() as conn:
        if await _is_processed(conn, event.event_id):
            log.debug("already_processed", event_id=event.event_id)
            return
        await _mark_processed(conn, event.event_id)

    if await _should_roll_window(redis, key, occurred_at):
        await _flush_window(event.tg_chat_id, redis, s3, db_pool, summary_engine, trace_id=event.trace_id)

    await redis.r.rpush(key, json.dumps(asdict(payload), ensure_ascii=False))
    size = await redis.r.llen(key)
    await redis.r.expire(key, max(settings.summarizer_time_window_minutes * 60, 3600))

    if size >= settings.summarizer_window_size:
        await _flush_window(event.tg_chat_id, redis, s3, db_pool, summary_engine, trace_id=event.trace_id)


async def _handle_edited_message(
    event: TelegramMessageEditedEvent,
    redis: RedisClient,
    db_pool: asyncpg.Pool,
) -> None:
    text = (event.new_text or "").strip()
    if not text:
        return

    async with db_pool.acquire() as conn:
        if await _is_processed(conn, event.event_id):
            log.debug("already_processed", event_id=event.event_id)
            return
        await _mark_processed(conn, event.event_id)

    key = _window_key(event.tg_chat_id)
    entries = await redis.r.lrange(key, 0, -1)
    if not entries:
        return

    updated: list[str] = []
    changed = False
    for raw_entry in entries:
        data = json.loads(raw_entry)
        if int(data["tg_message_id"]) == event.tg_message_id:
            data["text"] = text
            changed = True
        updated.append(json.dumps(data, ensure_ascii=False))

    if not changed:
        return

    await redis.r.delete(key)
    if updated:
        await redis.r.rpush(key, *updated)
        await redis.r.expire(key, max(settings.summarizer_time_window_minutes * 60, 3600))


async def _should_roll_window(redis: RedisClient, key: str, occurred_at: datetime) -> bool:
    last_entry = await redis.r.lindex(key, -1)
    if not last_entry:
        return False

    last_message = WindowMessage(**json.loads(last_entry))
    return needs_rollover(
        last_occurred_at=_parse_dt(last_message.occurred_at),
        occurred_at=occurred_at,
        strategy=settings.summarizer_strategy,
        time_window_minutes=settings.summarizer_time_window_minutes,
    )


async def _flush_window(
    tg_chat_id: int,
    redis: RedisClient,
    s3: S3Client,
    db_pool: asyncpg.Pool,
    summary_engine: ChatSummaryEngine,
    *,
    trace_id: str | None,
) -> None:
    key = _window_key(tg_chat_id)
    entries = await redis.r.lrange(key, 0, -1)
    if not entries:
        return

    messages = [WindowMessage(**json.loads(item)) for item in entries]
    llm_messages = [
        LlmWindowMessage(
            tg_message_id=message.tg_message_id,
            tg_sender_id=message.tg_sender_id,
            tg_sender_name=message.tg_sender_name,
            text=message.text,
            occurred_at=message.occurred_at,
        )
        for message in messages
    ]

    window_start = _parse_dt(messages[0].occurred_at)
    window_end = _parse_dt(messages[-1].occurred_at)
    summary = await summary_engine.summarize(llm_messages)

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            chat_id = await _ensure_chat(conn, tg_chat_id)
            await _refresh_chat_metadata(conn, chat_id, messages[-1])
            participants = await _ensure_participants(conn, messages)
            task_ids = await _find_window_task_ids(conn, tg_chat_id, [msg.tg_message_id for msg in messages])
            interaction_id = await _upsert_interaction(
                conn,
                chat_id=chat_id,
                window_start=window_start,
                window_end=window_end,
                participants=participants,
                topics=summary.topics,
                sentiment=summary.sentiment,
                summary_text=summary.summary,
                task_ids=task_ids,
            )
            object_key = None
            if s3.is_configured:
                object_key = await s3.put_bucket_object(
                    s3.bucket_raw,
                    f"interaction-windows/{interaction_id}.json",
                    json.dumps(
                        {
                            "tg_chat_id": tg_chat_id,
                            "window_start": window_start.isoformat(),
                            "window_end": window_end.isoformat(),
                            "messages": [asdict(msg) for msg in messages],
                        },
                        ensure_ascii=False,
                        default=str,
                    ).encode("utf-8"),
                    content_type="application/json",
                )
                await _set_interaction_object_ref(conn, interaction_id, object_key)

            updated_event = InteractionUpdatedEvent(
                interaction_id=interaction_id,
                chat_id=chat_id,
                window_start=window_start,
                window_end=window_end,
                participants=participants,
                topics=summary.topics,
                sentiment=summary.sentiment,
                summary=summary.summary,
                task_ids=task_ids,
                trace_id=trace_id,
            )
            await redis.xadd(STREAM_INTERACTION_UPDATED, {"data": updated_event.model_dump_json()})

    await redis.r.delete(key)
    log.info(
        "interaction_flushed",
        tg_chat_id=tg_chat_id,
        interaction_id=interaction_id,
        message_count=len(messages),
        topics=summary.topics,
        mode=summary_engine.mode,
    )


async def _upsert_interaction(
    conn: asyncpg.Connection,
    *,
    chat_id: str,
    window_start: datetime,
    window_end: datetime,
    participants: list[str],
    topics: list[str],
    sentiment: str,
    summary_text: str,
    task_ids: list[str],
) -> str:
    existing = await conn.fetchrow(
        """
        SELECT id, created_at
        FROM interaction
        WHERE chat_id = $1::uuid
          AND window_start = $2
        ORDER BY created_at DESC
        LIMIT 1
        """,
        chat_id,
        window_start,
    )
    if existing:
        await conn.execute(
            """
            UPDATE interaction
            SET window_end = $1,
                participants = $2::uuid[],
                topics = $3::text[],
                sentiment = $4,
                summary = $5,
                tasks = $6::uuid[]
            WHERE id = $7::uuid
              AND created_at = $8
            """,
            window_end,
            participants,
            topics,
            sentiment,
            summary_text,
            task_ids,
            existing["id"],
            existing["created_at"],
        )
        return str(existing["id"])

    row = await conn.fetchrow(
        """
        INSERT INTO interaction (
            chat_id,
            window_start,
            window_end,
            participants,
            topics,
            sentiment,
            summary,
            tasks
        ) VALUES (
            $1::uuid,
            $2,
            $3,
            $4::uuid[],
            $5::text[],
            $6,
            $7,
            $8::uuid[]
        )
        RETURNING id
        """,
        chat_id,
        window_start,
        window_end,
        participants,
        topics,
        sentiment,
        summary_text,
        task_ids,
    )
    return str(row["id"])


async def _set_interaction_object_ref(
    conn: asyncpg.Connection,
    interaction_id: str,
    source_object_ref: str,
) -> None:
    await conn.execute(
        """
        UPDATE interaction
        SET source_object_ref = $1
        WHERE id = $2::uuid
        """,
        source_object_ref,
        interaction_id,
    )


async def _ensure_chat(conn: asyncpg.Connection, tg_chat_id: int) -> str:
    row = await conn.fetchrow(
        """
        INSERT INTO chat (tg_chat_id, kind, metadata)
        VALUES ($1, 'private', '{}'::jsonb)
        ON CONFLICT (tg_chat_id) DO UPDATE
        SET updated_at = now()
        RETURNING id
        """,
        tg_chat_id,
    )
    return str(row["id"])


async def _refresh_chat_metadata(
    conn: asyncpg.Connection,
    chat_id: str,
    message: WindowMessage,
) -> None:
    await conn.execute(
        """
        UPDATE chat
        SET kind = $1,
            title = COALESCE($2, title),
            updated_at = now()
        WHERE id = $3::uuid
        """,
        message.chat_type,
        message.chat_title,
        chat_id,
    )


async def _ensure_participants(conn: asyncpg.Connection, messages: list[WindowMessage]) -> list[str]:
    participants: list[str] = []
    seen: set[int] = set()
    for message in messages:
        tg_user_id = message.tg_sender_id
        if tg_user_id is None or tg_user_id in seen:
            continue
        seen.add(tg_user_id)
        row = await conn.fetchrow(
            """
            INSERT INTO person (tg_user_id, display_name)
            VALUES ($1, $2)
            ON CONFLICT (tg_user_id) DO UPDATE
            SET display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), person.display_name),
                updated_at = now()
            RETURNING id
            """,
            tg_user_id,
            message.tg_sender_name or f"tg:{tg_user_id}",
        )
        participants.append(str(row["id"]))
    return participants


async def _find_window_task_ids(
    conn: asyncpg.Connection,
    tg_chat_id: int,
    message_ids: list[int],
) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT id
        FROM task
        WHERE (source_message_ref->>'tg_chat_id')::bigint = $1
          AND (source_message_ref->>'tg_message_id')::bigint = ANY($2::bigint[])
        ORDER BY created_at
        """,
        tg_chat_id,
        message_ids,
    )
    return [str(row["id"]) for row in rows]


def _window_key(tg_chat_id: int) -> str:
    return f"pil:summarizer:{tg_chat_id}:window"


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


async def run(
    redis: RedisClient,
    s3: S3Client,
    db_pool: asyncpg.Pool,
    summary_engine: ChatSummaryEngine,
) -> None:
    await _ensure_groups(redis)
    log.info(
        "consumer_started",
        streams=[settings.stream_message, settings.stream_message_edited],
        group=settings.consumer_group,
        strategy=settings.summarizer_strategy,
        window_size=settings.summarizer_window_size,
        llm_mode=summary_engine.mode,
    )

    while True:
        try:
            entries = await redis.xread_group(
                group=settings.consumer_group,
                consumer=settings.consumer_name,
                streams={
                    settings.stream_message: ">",
                    settings.stream_message_edited: ">",
                },
                count=settings.summarizer_batch_size,
                block=5000,
            )
        except Exception as exc:
            log.error("xreadgroup_error", error=str(exc))
            continue

        if not entries:
            continue

        for stream, messages in entries:
            for msg_id, fields in messages:
                try:
                    await _process_stream(stream, msg_id, fields, redis, s3, db_pool, summary_engine)
                except Exception as exc:
                    log.error("process_error", stream=stream, msg_id=msg_id, error=str(exc))
                    try:
                        await redis.xadd(
                            STREAM_DLQ_SUMMARIZER,
                            {
                                "stream": stream,
                                "msg_id": msg_id,
                                "error": str(exc),
                                "fields": json.dumps(fields, default=str),
                            },
                        )
                    except Exception:
                        pass
                finally:
                    await redis.xack(stream, settings.consumer_group, msg_id)
