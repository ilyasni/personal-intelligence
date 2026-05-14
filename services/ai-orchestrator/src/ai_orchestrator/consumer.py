# ruff: noqa: TC001,TC002
from __future__ import annotations

from contextlib import suppress
from datetime import UTC
from typing import Any

import asyncpg

from ai_orchestrator.graph import build_analysis_graph
from ai_orchestrator.llm import AnalysisRouter
from ai_orchestrator.preprocessing import build_window_id, needs_rollover
from ai_orchestrator.settings import settings
from pil_contracts import (
    STREAM_AI_ANALYSIS_COMPLETED,
    STREAM_AI_ANALYTICS_SIGNAL,
    STREAM_AI_PROJECTION_COMMAND,
    STREAM_AI_REPROCESS_WINDOW,
    STREAM_TELEGRAM_MESSAGE,
    STREAM_TELEGRAM_PREPROCESSED,
    AIAnalysisCompletedEvent,
    AnalyticsSignalEvent,
    ReprocessWindowCommand,
    TelegramMessageEvent,
    TelegramPreprocessedEvent,
    WindowMessagePayload,
)
from pil_observability import get_logger
from pil_storage import RedisClient

log = get_logger("ai-orchestrator.consumer")

_CONSUMER_NAME = "ai-orchestrator"


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
    for stream in (STREAM_TELEGRAM_MESSAGE, STREAM_AI_REPROCESS_WINDOW):
        with suppress(Exception):
            await redis.r.xgroup_create(stream, settings.consumer_group, id="$", mkstream=True)


def _window_key(tg_chat_id: int) -> str:
    return f"pil:ai-orchestrator:{tg_chat_id}:window"


async def _load_window_messages(redis: RedisClient, tg_chat_id: int) -> list[WindowMessagePayload]:
    entries = await redis.r.lrange(_window_key(tg_chat_id), 0, -1)
    return [WindowMessagePayload.model_validate_json(item) for item in entries]


async def _store_window_message(
    redis: RedisClient,
    tg_chat_id: int,
    payload: WindowMessagePayload,
) -> int:
    key = _window_key(tg_chat_id)
    await redis.r.rpush(key, payload.model_dump_json())
    await redis.r.expire(key, max(settings.analysis_time_window_minutes * 60, 3600))
    return int(await redis.r.llen(key))


async def _delete_window(redis: RedisClient, tg_chat_id: int) -> None:
    await redis.r.delete(_window_key(tg_chat_id))


async def _load_canonical_context(
    pool: asyncpg.Pool,
    tg_chat_id: int,
    messages: list[WindowMessagePayload],
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        owner_row = await conn.fetchrow(
            """
            SELECT id, tg_user_id, display_name, topics, organizations
            FROM person
            WHERE is_owner = TRUE
            ORDER BY updated_at DESC
            LIMIT 1
            """
        )
        people_rows = await conn.fetch(
            """
            SELECT p.id, p.tg_user_id, p.display_name, p.username, p.topics
            FROM chat c
            JOIN chat_membership cm ON cm.chat_id = c.id
            JOIN person p ON p.id = cm.person_id
            WHERE c.tg_chat_id = $1
            ORDER BY p.updated_at DESC
            LIMIT 12
            """,
            tg_chat_id,
        )
        interaction_rows = await conn.fetch(
            """
            SELECT aw.summary, aw.analysis_payload
            FROM analysis_window aw
            WHERE aw.tg_chat_id = $1
            ORDER BY aw.window_end DESC
            LIMIT 5
            """,
            tg_chat_id,
        )
        task_rows = await conn.fetch(
            """
            SELECT title, status, due_at
            FROM task
            WHERE chat_id = (
                SELECT id FROM chat WHERE tg_chat_id = $1 LIMIT 1
            )
              AND status = 'open'
            ORDER BY created_at DESC
            LIMIT 10
            """,
            tg_chat_id,
        )

    return {
        "owner": dict(owner_row) if owner_row else None,
        "known_people": [dict(row) for row in people_rows],
        "recent_windows": [
            {
                "summary": row["summary"],
                "topics": ((row["analysis_payload"] or {}).get("topics") if row["analysis_payload"] else []),
            }
            for row in interaction_rows
        ],
        "open_tasks": [dict(row) for row in task_rows],
        "current_participants": sorted({msg.tg_sender_id for msg in messages if msg.tg_sender_id is not None}),
    }


async def _handle_message(
    event: TelegramMessageEvent,
    redis: RedisClient,
    db_pool: asyncpg.Pool,
    analysis_graph: Any,
) -> None:
    if not (event.text or "").strip() and not event.media_type:
        return

    payload = WindowMessagePayload(
        tg_message_id=event.tg_message_id,
        tg_sender_id=event.tg_sender_id,
        tg_sender_name=event.tg_sender_name,
        tg_sender_username=event.tg_sender_username,
        text=(event.text or "").strip(),
        reply_to_message_id=event.reply_to_message_id,
        media_type=event.media_type,
        is_forwarded=event.is_forwarded,
        occurred_at=(event.tg_date or event.occurred_at).astimezone(UTC),
    )

    async with db_pool.acquire() as conn:
        if await _is_processed(conn, event.event_id):
            return
        await _mark_processed(conn, event.event_id)

    existing_window = await _load_window_messages(redis, event.tg_chat_id)
    if existing_window:
        last_message = existing_window[-1]
        if needs_rollover(
            last_occurred_at=last_message.occurred_at,
            occurred_at=payload.occurred_at,
            strategy=settings.window_strategy,
            time_window_minutes=settings.analysis_time_window_minutes,
        ):
            await _flush_window(
                redis=redis,
                db_pool=db_pool,
                analysis_graph=analysis_graph,
                tg_chat_id=event.tg_chat_id,
                source_event_id=event.event_id,
                chat_type=event.chat_type,
                trace_id=event.trace_id,
            )

    size = await _store_window_message(redis, event.tg_chat_id, payload)
    if size >= settings.analysis_window_size:
        await _flush_window(
            redis=redis,
            db_pool=db_pool,
            analysis_graph=analysis_graph,
            tg_chat_id=event.tg_chat_id,
            source_event_id=event.event_id,
            chat_type=event.chat_type,
            trace_id=event.trace_id,
        )


async def _handle_reprocess(
    command: ReprocessWindowCommand,
    redis: RedisClient,
    db_pool: asyncpg.Pool,
    analysis_graph: Any,
) -> None:
    async with db_pool.acquire() as conn:
        if await _is_processed(conn, command.command_id):
            return
        row = await conn.fetchrow(
            """
            SELECT tg_chat_id, chat_type, messages
            FROM analysis_window
            WHERE id = $1::uuid
            """,
            command.window_id,
        )
        if row is None:
            await _mark_processed(conn, command.command_id)
            return
        await _mark_processed(conn, command.command_id)

    messages = [WindowMessagePayload.model_validate(item) for item in (row["messages"] or [])]
    await _run_analysis(
        redis=redis,
        db_pool=db_pool,
        analysis_graph=analysis_graph,
        tg_chat_id=int(row["tg_chat_id"]),
        chat_type=str(row["chat_type"]),
        messages=messages,
        source_window_id=command.window_id,
        source_event_id=command.command_id,
        trace_id=command.trace_id,
    )


async def _flush_window(
    *,
    redis: RedisClient,
    db_pool: asyncpg.Pool,
    analysis_graph: Any,
    tg_chat_id: int,
    source_event_id: str,
    chat_type: str,
    trace_id: str | None,
) -> None:
    messages = await _load_window_messages(redis, tg_chat_id)
    if not messages:
        return
    await _delete_window(redis, tg_chat_id)
    await _run_analysis(
        redis=redis,
        db_pool=db_pool,
        analysis_graph=analysis_graph,
        tg_chat_id=tg_chat_id,
        chat_type=chat_type,
        messages=messages,
        source_window_id=build_window_id(),
        source_event_id=source_event_id,
        trace_id=trace_id,
    )


async def _run_analysis(
    *,
    redis: RedisClient,
    db_pool: asyncpg.Pool,
    analysis_graph: Any,
    tg_chat_id: int,
    chat_type: str,
    messages: list[WindowMessagePayload],
    source_window_id: str,
    source_event_id: str,
    trace_id: str | None,
) -> None:
    graph_state = await analysis_graph.ainvoke(
        {
            "source_event_id": source_event_id,
            "source_window_id": source_window_id,
            "tg_chat_id": tg_chat_id,
            "chat_type": chat_type,
            "messages": messages,
            "trace_id": trace_id,
        }
    )
    features = graph_state["features"]
    result = graph_state["result"]
    projection_command = graph_state["projection_command"]

    preprocessed_event = TelegramPreprocessedEvent(
        source_event_id=source_event_id,
        tg_chat_id=tg_chat_id,
        source_window_id=source_window_id,
        messages=messages,
        features=features,
        trace_id=trace_id,
    )
    completed_event = AIAnalysisCompletedEvent(
        source_event_id=source_event_id,
        tg_chat_id=tg_chat_id,
        source_window_id=source_window_id,
        result=result,
        trace_id=trace_id,
    )

    await redis.xadd(STREAM_TELEGRAM_PREPROCESSED, {"data": preprocessed_event.model_dump_json()})
    await redis.xadd(STREAM_AI_ANALYSIS_COMPLETED, {"data": completed_event.model_dump_json()})
    for signal in result.analytics_signals:
        signal_event = AnalyticsSignalEvent(
            source_window_id=source_window_id,
            tg_chat_id=tg_chat_id,
            signal=signal,
            trace_id=trace_id,
        )
        await redis.xadd(STREAM_AI_ANALYTICS_SIGNAL, {"data": signal_event.model_dump_json()})
    await redis.xadd(STREAM_AI_PROJECTION_COMMAND, {"data": projection_command.model_dump_json()})
    log.info(
        "analysis_emitted",
        tg_chat_id=tg_chat_id,
        source_window_id=source_window_id,
        message_count=len(messages),
        topics=result.topics,
    )


async def run(redis: RedisClient, db_pool: asyncpg.Pool, router: AnalysisRouter) -> None:
    await _ensure_groups(redis)
    analysis_graph = build_analysis_graph(
        router=router,
        context_loader=lambda tg_chat_id, messages: _load_canonical_context(db_pool, tg_chat_id, messages),
    )
    log.info(
        "consumer_started",
        group=settings.consumer_group,
        window_strategy=settings.window_strategy,
        window_size=settings.analysis_window_size,
    )

    while True:
        try:
            entries = await redis.xread_group(
                group=settings.consumer_group,
                consumer=settings.consumer_name,
                streams={
                    STREAM_TELEGRAM_MESSAGE: ">",
                    STREAM_AI_REPROCESS_WINDOW: ">",
                },
                count=settings.analysis_batch_size,
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
                    raw = str(fields.get("data", "{}"))
                    if stream == STREAM_TELEGRAM_MESSAGE:
                        await _handle_message(
                            TelegramMessageEvent.model_validate_json(raw),
                            redis,
                            db_pool,
                            analysis_graph,
                        )
                    elif stream == STREAM_AI_REPROCESS_WINDOW:
                        await _handle_reprocess(
                            ReprocessWindowCommand.model_validate_json(raw),
                            redis,
                            db_pool,
                            analysis_graph,
                        )
                except Exception as exc:
                    log.error("process_error", stream=stream, msg_id=msg_id, error=str(exc))
                finally:
                    await redis.xack(stream, settings.consumer_group, msg_id)
