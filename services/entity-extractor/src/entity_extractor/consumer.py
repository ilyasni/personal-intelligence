"""Redis Streams consumer: events.telegram.message → entity extraction → publish."""
import json
from datetime import datetime, timezone

import asyncpg
import structlog
from pil_contracts import (
    EntityCandidate,
    EntityFoundEvent,
    TelegramMessageEvent,
    STREAM_ENTITY_FOUND,
    STREAM_DLQ_ENTITY,
)
from pil_storage import RedisClient

from entity_extractor.extractor import extract
from entity_extractor.reconcile import find_person_id, insert_mention, upsert_topic
from entity_extractor.settings import settings

log = structlog.get_logger("entity-extractor.consumer")

_CONSUMER_NAME = "entity-extractor"


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


async def _ensure_group(redis: RedisClient) -> None:
    try:
        await redis.r.xgroup_create(settings.stream_in, settings.consumer_group, id="0", mkstream=True)
    except Exception:
        pass  # group already exists


async def _process_one(
    msg_id: str,
    fields: dict,
    redis: RedisClient,
    db_pool: asyncpg.Pool,
) -> None:
    raw = fields.get("data", "{}")
    try:
        event = TelegramMessageEvent.model_validate_json(raw)
    except Exception as exc:
        log.warning("parse_error", msg_id=msg_id, error=str(exc))
        return

    text = event.text
    if not text:
        return

    async with db_pool.acquire() as conn:
        if await _is_processed(conn, event.event_id):
            log.debug("already_processed", event_id=event.event_id)
            return

        lang, raw_entities = extract(text, min_confidence=settings.entity_min_confidence)

        candidates: list[EntityCandidate] = []
        for ent in raw_entities:
            person_id: str | None = None

            if ent.kind == "person":
                person_id = await find_person_id(
                    conn,
                    tg_user_id=event.tg_sender_id,
                    display_name=ent.surface,
                )
                # Write mention only when both speaker and mentioned are known persons
                if person_id and event.tg_sender_id:
                    speaker_id = await find_person_id(conn, tg_user_id=event.tg_sender_id)
                    chat_row = await conn.fetchrow(
                        "SELECT id FROM chat WHERE tg_chat_id = $1", event.tg_chat_id
                    )
                    if speaker_id and chat_row:
                        await insert_mention(
                            conn,
                            chat_uuid=str(chat_row["id"]),
                            speaker_uuid=speaker_id,
                            mentioned_uuid=person_id,
                            message_ref={
                                "tg_chat_id": event.tg_chat_id,
                                "tg_message_id": event.tg_message_id,
                            },
                            context=text[:200],
                        )

            elif ent.kind == "topic":
                slug = ent.normalized.replace(" ", "-")
                await upsert_topic(conn, slug=slug, display_name=ent.surface)

            candidates.append(
                EntityCandidate(
                    kind=ent.kind,
                    surface=ent.surface,
                    normalized=ent.normalized,
                    confidence=ent.confidence,
                    person_id=person_id,
                )
            )

        found_event = EntityFoundEvent(
            source_event_id=event.event_id,
            tg_chat_id=event.tg_chat_id,
            tg_message_id=event.tg_message_id,
            tg_sender_id=event.tg_sender_id,
            language=lang,
            entities=candidates,
            trace_id=event.trace_id,
        )

        await redis.xadd(STREAM_ENTITY_FOUND, {"data": found_event.model_dump_json()})
        await _mark_processed(conn, event.event_id)

    log.info(
        "processed",
        event_id=event.event_id,
        lang=lang,
        entity_count=len(candidates),
    )


async def run(redis: RedisClient, db_pool: asyncpg.Pool) -> None:
    await _ensure_group(redis)
    log.info("consumer_started", stream=settings.stream_in, group=settings.consumer_group)

    while True:
        try:
            entries = await redis.xread_group(
                group=settings.consumer_group,
                consumer=settings.consumer_name,
                streams={settings.stream_in: ">"},
                count=settings.entity_batch_size,
                block=5000,
            )
        except Exception as exc:
            log.error("xreadgroup_error", error=str(exc))
            continue

        if not entries:
            continue

        for _stream, messages in entries:
            for msg_id, fields in messages:
                try:
                    await _process_one(msg_id, fields, redis, db_pool)
                except Exception as exc:
                    log.error("process_error", msg_id=msg_id, error=str(exc))
                    try:
                        await redis.xadd(STREAM_DLQ_ENTITY, {"msg_id": msg_id, "error": str(exc), "fields": json.dumps(fields)})
                    except Exception:
                        pass
                finally:
                    await redis.xack(settings.stream_in, settings.consumer_group, msg_id)
