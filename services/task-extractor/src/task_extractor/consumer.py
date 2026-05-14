"""Redis Streams consumer: task extraction and resolution."""

import json
from datetime import datetime, timezone

import asyncpg
import structlog
from pil_contracts import (
    STREAM_DLQ_TASK,
    STREAM_TASK_CREATED,
    STREAM_TASK_RESOLVED,
    TaskCreatedEvent,
    TaskResolvedEvent,
    TelegramMessageDeletedEvent,
    TelegramMessageEditedEvent,
    TelegramMessageEvent,
)
from pil_storage import RedisClient

from task_extractor.rules import TaskCandidate, detect_resolution, extract_task_candidate
from task_extractor.settings import settings

log = structlog.get_logger("task-extractor.consumer")

_CONSUMER_NAME = "task-extractor"


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
    for stream in (settings.stream_message, settings.stream_message_edited, settings.stream_message_deleted):
        try:
            await redis.r.xgroup_create(stream, settings.consumer_group, id="$", mkstream=True)
        except Exception:
            pass


async def _process_stream(
    stream: str,
    msg_id: str,
    fields: dict,
    redis: RedisClient,
    db_pool: asyncpg.Pool,
) -> None:
    raw = fields.get("data", "{}")
    if stream == settings.stream_message:
        event = TelegramMessageEvent.model_validate_json(raw)
        await _handle_message(event, redis, db_pool)
        return
    if stream == settings.stream_message_edited:
        event = TelegramMessageEditedEvent.model_validate_json(raw)
        await _handle_message_edited(event, redis, db_pool)
        return
    if stream == settings.stream_message_deleted:
        event = TelegramMessageDeletedEvent.model_validate_json(raw)
        await _handle_message_deleted(event, redis, db_pool)
        return
    log.warning("unknown_stream", stream=stream, msg_id=msg_id)


async def _handle_message(
    event: TelegramMessageEvent,
    redis: RedisClient,
    db_pool: asyncpg.Pool,
) -> None:
    text = (event.text or "").strip()
    if not text:
        return

    async with db_pool.acquire() as conn:
        if await _is_processed(conn, event.event_id):
            log.debug("already_processed", event_id=event.event_id)
            return

        if detect_resolution(text):
            resolved = await _resolve_replied_task(conn, event, redis, evidence=text)
            if resolved:
                await _mark_processed(conn, event.event_id)
                log.info("task_resolved", event_id=event.event_id, task_id=resolved)
                return

        candidate = extract_task_candidate(text, now=event.occurred_at)
        if not candidate or candidate.confidence < settings.task_min_confidence:
            await _mark_processed(conn, event.event_id)
            return

        existing = await _find_task_by_source_message(conn, event.tg_chat_id, event.tg_message_id)
        if existing:
            await _mark_processed(conn, event.event_id)
            return

        created_task_id = await _create_task(conn, event, candidate)
        created_event = await _build_task_created_event(conn, created_task_id, event, candidate)
        await redis.xadd(STREAM_TASK_CREATED, {"data": created_event.model_dump_json()})
        await _mark_processed(conn, event.event_id)

    log.info(
        "task_created",
        event_id=event.event_id,
        task_id=created_task_id,
        confidence=candidate.confidence,
        kind=candidate.kind,
    )


async def _handle_message_edited(
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

        existing = await _find_task_by_source_message(conn, event.tg_chat_id, event.tg_message_id)
        if not existing:
            await _mark_processed(conn, event.event_id)
            return

        candidate = extract_task_candidate(text, now=event.occurred_at)
        if candidate:
            await conn.execute(
                """
                UPDATE task
                SET title = $1,
                    description = $2,
                    due_at = $3,
                    priority = $4,
                    confidence = $5,
                    evidence = $6,
                    updated_at = now()
                WHERE id = $7::uuid AND status = 'open'
                """,
                candidate.title,
                candidate.description,
                candidate.due_at,
                candidate.priority,
                candidate.confidence,
                candidate.evidence,
                existing["id"],
            )

        await _mark_processed(conn, event.event_id)

    log.info("task_updated_from_edit", event_id=event.event_id, task_id=str(existing["id"]))


async def _handle_message_deleted(
    event: TelegramMessageDeletedEvent,
    redis: RedisClient,
    db_pool: asyncpg.Pool,
) -> None:
    if not event.tg_message_ids:
        return

    async with db_pool.acquire() as conn:
        if await _is_processed(conn, event.event_id):
            log.debug("already_processed", event_id=event.event_id)
            return

        rows = await conn.fetch(
            """
            UPDATE task
            SET status = 'dropped',
                resolved_at = now(),
                updated_at = now(),
                evidence = COALESCE(evidence, 'source message deleted')
            WHERE status = 'open'
              AND (source_message_ref->>'tg_chat_id')::bigint = $1
              AND (source_message_ref->>'tg_message_id')::bigint = ANY($2::bigint[])
            RETURNING id
            """,
            event.tg_chat_id,
            event.tg_message_ids,
        )

        for row in rows:
            resolved_event = TaskResolvedEvent(
                task_id=str(row["id"]),
                resolution="dropped",
                evidence="source message deleted",
                trace_id=event.trace_id,
            )
            await redis.xadd(STREAM_TASK_RESOLVED, {"data": resolved_event.model_dump_json()})

        await _mark_processed(conn, event.event_id)

    if rows:
        log.info("tasks_dropped", event_id=event.event_id, count=len(rows))


async def _create_task(
    conn: asyncpg.Connection,
    event: TelegramMessageEvent,
    candidate: TaskCandidate,
) -> str:
    chat_id = await _ensure_chat(conn, event)
    sender_person_id = await _ensure_person(
        conn,
        tg_user_id=event.tg_sender_id,
        username=event.tg_sender_username,
        display_name=event.tg_sender_name,
    )
    owner_record_id = await _get_owner_person_id(conn)

    owner_person_id: str | None = sender_person_id
    counterpart_person_id: str | None = None

    if candidate.kind == "request":
        owner_person_id = owner_record_id or sender_person_id
        counterpart_person_id = sender_person_id if owner_person_id != sender_person_id else None
    elif sender_person_id and owner_record_id and sender_person_id != owner_record_id:
        counterpart_person_id = owner_record_id

    row = await conn.fetchrow(
        """
        INSERT INTO task (
            title,
            description,
            owner_person_id,
            counterpart_person_id,
            chat_id,
            source_message_ref,
            due_at,
            status,
            priority,
            confidence,
            evidence
        ) VALUES (
            $1,
            $2,
            $3::uuid,
            $4::uuid,
            $5::uuid,
            $6::jsonb,
            $7,
            'open',
            $8,
            $9,
            $10
        )
        RETURNING id
        """,
        candidate.title,
        candidate.description,
        owner_person_id,
        counterpart_person_id,
        chat_id,
        json.dumps(
            {
                "tg_chat_id": event.tg_chat_id,
                "tg_message_id": event.tg_message_id,
            }
        ),
        candidate.due_at,
        candidate.priority,
        candidate.confidence,
        candidate.evidence,
    )
    return str(row["id"])


async def _build_task_created_event(
    conn: asyncpg.Connection,
    task_id: str,
    event: TelegramMessageEvent,
    candidate: TaskCandidate,
) -> TaskCreatedEvent:
    row = await conn.fetchrow(
        """
        SELECT owner_person_id, counterpart_person_id
        FROM task
        WHERE id = $1::uuid
        """,
        task_id,
    )
    return TaskCreatedEvent(
        task_id=task_id,
        title=candidate.title,
        owner_person_id=str(row["owner_person_id"]) if row and row["owner_person_id"] else None,
        counterpart_person_id=str(row["counterpart_person_id"]) if row and row["counterpart_person_id"] else None,
        due_at=candidate.due_at,
        source_message_ref={
            "tg_chat_id": event.tg_chat_id,
            "tg_message_id": event.tg_message_id,
        },
        confidence=candidate.confidence,
        evidence=candidate.evidence,
        trace_id=event.trace_id,
    )


async def _resolve_replied_task(
    conn: asyncpg.Connection,
    event: TelegramMessageEvent,
    redis: RedisClient,
    *,
    evidence: str,
) -> str | None:
    if not event.reply_to_message_id:
        return None

    row = await conn.fetchrow(
        """
        UPDATE task
        SET status = 'done',
            resolved_at = $1,
            updated_at = now()
        WHERE status = 'open'
          AND (source_message_ref->>'tg_chat_id')::bigint = $2
          AND (source_message_ref->>'tg_message_id')::bigint = $3
        RETURNING id
        """,
        event.occurred_at or datetime.now(timezone.utc),
        event.tg_chat_id,
        event.reply_to_message_id,
    )
    if not row:
        return None

    resolved_event = TaskResolvedEvent(
        task_id=str(row["id"]),
        resolution="done",
        evidence=evidence[:400],
        trace_id=event.trace_id,
    )
    await redis.xadd(STREAM_TASK_RESOLVED, {"data": resolved_event.model_dump_json()})
    return str(row["id"])


async def _find_task_by_source_message(
    conn: asyncpg.Connection,
    tg_chat_id: int,
    tg_message_id: int,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT id, status
        FROM task
        WHERE (source_message_ref->>'tg_chat_id')::bigint = $1
          AND (source_message_ref->>'tg_message_id')::bigint = $2
        ORDER BY created_at DESC
        LIMIT 1
        """,
        tg_chat_id,
        tg_message_id,
    )


async def _ensure_chat(conn: asyncpg.Connection, event: TelegramMessageEvent) -> str | None:
    row = await conn.fetchrow(
        """
        INSERT INTO chat (tg_chat_id, kind, title, metadata)
        VALUES ($1, $2, $3, '{}'::jsonb)
        ON CONFLICT (tg_chat_id) DO UPDATE
        SET kind = EXCLUDED.kind,
            title = COALESCE(EXCLUDED.title, chat.title),
            updated_at = now()
        RETURNING id
        """,
        event.tg_chat_id,
        event.chat_type,
        event.chat_title,
    )
    return str(row["id"]) if row else None


async def _ensure_person(
    conn: asyncpg.Connection,
    *,
    tg_user_id: int | None,
    username: str | None,
    display_name: str | None,
) -> str | None:
    if tg_user_id is None:
        return None

    row = await conn.fetchrow(
        """
        INSERT INTO person (tg_user_id, username, display_name)
        VALUES ($1, $2, $3)
        ON CONFLICT (tg_user_id) DO UPDATE
        SET username = COALESCE(EXCLUDED.username, person.username),
            display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), person.display_name),
            updated_at = now()
        RETURNING id
        """,
        tg_user_id,
        username,
        display_name or f"tg:{tg_user_id}",
    )
    return str(row["id"]) if row else None


async def _get_owner_person_id(conn: asyncpg.Connection) -> str | None:
    row = await conn.fetchrow(
        """
        SELECT id
        FROM person
        WHERE is_owner = TRUE
        ORDER BY updated_at DESC
        LIMIT 1
        """
    )
    return str(row["id"]) if row else None


async def run(redis: RedisClient, db_pool: asyncpg.Pool) -> None:
    await _ensure_groups(redis)
    log.info(
        "consumer_started",
        streams=[
            settings.stream_message,
            settings.stream_message_edited,
            settings.stream_message_deleted,
        ],
        group=settings.consumer_group,
    )

    while True:
        try:
            entries = await redis.xread_group(
                group=settings.consumer_group,
                consumer=settings.consumer_name,
                streams={
                    settings.stream_message: ">",
                    settings.stream_message_edited: ">",
                    settings.stream_message_deleted: ">",
                },
                count=settings.task_batch_size,
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
                    await _process_stream(stream, msg_id, fields, redis, db_pool)
                except Exception as exc:
                    log.error("process_error", stream=stream, msg_id=msg_id, error=str(exc))
                    try:
                        await redis.xadd(
                            STREAM_DLQ_TASK,
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
