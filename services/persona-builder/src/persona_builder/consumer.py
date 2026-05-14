"""Redis Streams consumer: events.processing.entity_found → person profile update."""
import structlog
import asyncpg

from pil_contracts import EntityFoundEvent, STREAM_PERSON_UPDATED, PersonUpdatedEvent
from pil_storage import RedisClient

from persona_builder.aggregator import update_person_from_event
from persona_builder.settings import settings

log = structlog.get_logger("persona-builder.consumer")

_CONSUMER_NAME = "persona-builder"


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
        pass


async def _process_one(
    msg_id: str,
    fields: dict,
    redis: RedisClient,
    db_pool: asyncpg.Pool,
) -> None:
    raw = fields.get("data", "{}")
    try:
        event = EntityFoundEvent.model_validate_json(raw)
    except Exception as exc:
        log.warning("parse_error", msg_id=msg_id, error=str(exc))
        return

    organizations = [e.normalized for e in event.entities if e.kind == "organization"]
    topics = [e.normalized for e in event.entities if e.kind == "topic"]

    if not organizations and not topics:
        async with db_pool.acquire() as conn:
            await _mark_processed(conn, event.event_id)
        return

    async with db_pool.acquire() as conn:
        if await _is_processed(conn, event.event_id):
            log.debug("already_processed", event_id=event.event_id)
            return

        person_id = await update_person_from_event(
            conn,
            tg_sender_id=event.tg_sender_id,
            tg_chat_id=event.tg_chat_id,
            organizations=organizations,
            topics=topics,
            occurred_at=event.occurred_at,
        )

        if person_id:
            person_row = await conn.fetchrow(
                "SELECT tg_user_id, display_name, organizations, topics, trust_score FROM person WHERE id = $1::uuid",
                person_id,
            )
            if person_row:
                updated = PersonUpdatedEvent(
                    person_id=person_id,
                    tg_user_id=person_row["tg_user_id"],
                    display_name=person_row["display_name"],
                    organizations=list(person_row["organizations"] or []),
                    topics=list(person_row["topics"] or []),
                    trust_score=float(person_row["trust_score"]),
                    trace_id=event.trace_id,
                )
                await redis.xadd(STREAM_PERSON_UPDATED, {"data": updated.model_dump_json()})

        await _mark_processed(conn, event.event_id)

    log.info(
        "processed",
        event_id=event.event_id,
        person_id=person_id,
        new_orgs=len(organizations),
        new_topics=len(topics),
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
                count=settings.persona_batch_size,
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
                finally:
                    await redis.xack(settings.stream_in, settings.consumer_group, msg_id)
