# ruff: noqa: TC001,TC002
from __future__ import annotations

import json
from contextlib import suppress
from decimal import Decimal
from itertools import combinations
from typing import Any

import asyncpg
from neo4j import AsyncGraphDatabase

from memory_projector.settings import settings
from pil_contracts import (
    STREAM_AI_EMBEDDING_REQUESTED,
    STREAM_INTERACTION_UPDATED,
    EmbeddingJob,
    InteractionUpdatedEvent,
    ProjectionCommand,
)
from pil_observability import get_logger
from pil_storage import RedisClient, S3Client

log = get_logger("memory-projector.consumer")

_CONSUMER_NAME = "memory-projector"


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
    with suppress(Exception):
        await redis.r.xgroup_create(settings.stream_projection, settings.consumer_group, id="$", mkstream=True)


async def _ensure_chat(conn: asyncpg.Connection, command: ProjectionCommand) -> str:
    title = next(
        (message.tg_sender_name for message in command.messages if message.tg_sender_name),
        None,
    )
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
        command.tg_chat_id,
        command.features.chat_type,
        title,
    )
    return str(row["id"])


async def _ensure_person(
    conn: asyncpg.Connection,
    *,
    tg_user_id: int,
    username: str | None,
    display_name: str | None,
    topics: list[str],
    last_interaction_at: Any,
) -> str:
    is_owner = _matches_owner_identity(
        tg_user_id=tg_user_id,
        username=username,
        display_name=display_name,
    )
    effective_display_name = display_name or f"tg:{tg_user_id}"
    if is_owner and settings.owner_primary_display_name.strip():
        effective_display_name = settings.owner_primary_display_name.strip()
    row = await conn.fetchrow(
        """
        INSERT INTO person (tg_user_id, username, display_name, topics, last_interaction_at, is_owner)
        VALUES ($1, $2, $3, $4::text[], $5, $6)
        ON CONFLICT (tg_user_id) DO UPDATE
        SET username = COALESCE(EXCLUDED.username, person.username),
            display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), person.display_name),
            topics = (
                SELECT ARRAY(
                    SELECT DISTINCT value
                    FROM unnest(COALESCE(person.topics, '{}'::text[]) || COALESCE(EXCLUDED.topics, '{}'::text[])) AS value
                    WHERE value <> ''
                )
            ),
            last_interaction_at = GREATEST(person.last_interaction_at, EXCLUDED.last_interaction_at),
            is_owner = person.is_owner OR EXCLUDED.is_owner,
            updated_at = now()
        RETURNING id
        """,
        tg_user_id,
        username,
        effective_display_name,
        topics,
        last_interaction_at,
        is_owner,
    )
    return str(row["id"])


def _matches_owner_identity(
    *,
    tg_user_id: int,
    username: str | None,
    display_name: str | None,
) -> bool:
    if tg_user_id in settings.owner_tg_user_id_set():
        return True
    normalized_username = (username or "").strip().lstrip("@").casefold()
    if normalized_username and normalized_username in settings.owner_username_set():
        return True
    normalized_display_name = (display_name or "").strip().casefold()
    return bool(
        normalized_display_name
        and normalized_display_name in settings.owner_display_name_set()
    )


async def _ensure_participants(
    conn: asyncpg.Connection,
    chat_id: str,
    command: ProjectionCommand,
) -> dict[int, str]:
    participant_map: dict[int, str] = {}
    for message in command.messages:
        if message.tg_sender_id is None:
            continue
        if message.tg_sender_id in participant_map:
            continue
        person_id = await _ensure_person(
            conn,
            tg_user_id=message.tg_sender_id,
            username=message.tg_sender_username,
            display_name=message.tg_sender_name,
            topics=command.result.topics[:8],
            last_interaction_at=message.occurred_at,
        )
        participant_map[message.tg_sender_id] = person_id
        await conn.execute(
            """
            INSERT INTO chat_membership (chat_id, person_id)
            VALUES ($1::uuid, $2::uuid)
            ON CONFLICT DO NOTHING
            """,
            chat_id,
            person_id,
        )
    return participant_map


async def _upsert_analysis_window(
    conn: asyncpg.Connection,
    *,
    chat_id: str,
    participant_map: dict[int, str],
    command: ProjectionCommand,
) -> str:
    window_start = command.messages[0].occurred_at
    window_end = command.messages[-1].occurred_at
    messages = [message.model_dump(mode="json") for message in command.messages]
    features = command.features.model_dump(mode="json")
    analysis_payload = command.result.model_dump(mode="json")

    row = await conn.fetchrow(
        """
        INSERT INTO analysis_window (
            id,
            chat_id,
            tg_chat_id,
            source_message_ids,
            participant_tg_ids,
            chat_type,
            window_start,
            window_end,
            messages,
            features,
            analysis_payload,
            summary,
            confidence
        ) VALUES (
            $1::uuid,
            $2::uuid,
            $3,
            $4::bigint[],
            $5::bigint[],
            $6,
            $7,
            $8,
            $9::jsonb,
            $10::jsonb,
            $11::jsonb,
            $12,
            $13
        )
        ON CONFLICT (id) DO UPDATE
        SET window_end = EXCLUDED.window_end,
            source_message_ids = EXCLUDED.source_message_ids,
            participant_tg_ids = EXCLUDED.participant_tg_ids,
            messages = EXCLUDED.messages,
            features = EXCLUDED.features,
            analysis_payload = EXCLUDED.analysis_payload,
            summary = EXCLUDED.summary,
            confidence = EXCLUDED.confidence,
            updated_at = now()
        RETURNING id
        """,
        command.source_window_id,
        chat_id,
        command.tg_chat_id,
        [message.tg_message_id for message in command.messages],
        sorted(participant_map.keys()),
        command.features.chat_type,
        window_start,
        window_end,
        json.dumps(messages, ensure_ascii=False, default=str),
        json.dumps(features, ensure_ascii=False, default=str),
        json.dumps(analysis_payload, ensure_ascii=False, default=str),
        command.result.summary,
        Decimal(str(command.result.confidence)),
    )
    return str(row["id"])


async def _replace_facts(conn: asyncpg.Connection, window_id: str, command: ProjectionCommand) -> None:
    await conn.execute("DELETE FROM extracted_fact WHERE window_id = $1::uuid", window_id)
    for claim in command.result.claims:
        await conn.execute(
            """
            INSERT INTO extracted_fact (
                window_id,
                fact_type,
                subject_text,
                predicate,
                object_text,
                claim_text,
                confidence,
                evidence_message_ids,
                caveats,
                metadata
            ) VALUES (
                $1::uuid, $2, $3, $4, $5, $6, $7, $8::bigint[], $9::text[], $10::jsonb
            )
            """,
            window_id,
            claim.kind,
            claim.subject,
            claim.predicate,
            claim.object,
            claim.claim,
            Decimal(str(claim.confidence)),
            claim.evidence_message_ids,
            claim.caveats,
            json.dumps({"source_window_id": command.source_window_id}, ensure_ascii=False),
        )


async def _replace_signals(conn: asyncpg.Connection, window_id: str, command: ProjectionCommand) -> None:
    await conn.execute("DELETE FROM analytics_signal WHERE window_id = $1::uuid", window_id)
    for signal in command.result.analytics_signals:
        await conn.execute(
            """
            INSERT INTO analytics_signal (
                window_id,
                tg_chat_id,
                signal_kind,
                score,
                summary,
                evidence_message_ids,
                payload
            ) VALUES (
                $1::uuid, $2, $3, $4, $5, $6::bigint[], $7::jsonb
            )
            """,
            window_id,
            command.tg_chat_id,
            signal.kind,
            Decimal(str(signal.score)),
            signal.summary,
            signal.evidence_message_ids,
            json.dumps(signal.payload, ensure_ascii=False, default=str),
        )


async def _find_task_for_evidence(
    conn: asyncpg.Connection,
    chat_id: str,
    evidence_message_id: int,
) -> str | None:
    row = await conn.fetchrow(
        """
        SELECT id
        FROM task
        WHERE chat_id = $1::uuid
          AND (source_message_ref->>'tg_message_id')::bigint = $2
        ORDER BY
          CASE WHEN owner_person_id IS NOT NULL THEN 0 ELSE 1 END,
          updated_at DESC,
          created_at DESC
        LIMIT 1
        """,
        chat_id,
        evidence_message_id,
    )
    return str(row["id"]) if row else None


async def _sync_tasks(
    conn: asyncpg.Connection,
    *,
    chat_id: str,
    participant_map: dict[int, str],
    command: ProjectionCommand,
) -> list[str]:
    owner_person_id = None
    owner_row = await conn.fetchrow(
        "SELECT id FROM person WHERE is_owner = TRUE ORDER BY updated_at DESC LIMIT 1"
    )
    if owner_row:
        owner_person_id = str(owner_row["id"])

    tasks: list[str] = []
    first_counterpart = next(iter(participant_map.values()), None)
    for task in command.result.tasks:
        evidence_id = task.evidence_message_ids[0] if task.evidence_message_ids else 0
        existing_id = await _find_task_for_evidence(conn, chat_id, evidence_id)
        if existing_id:
            await conn.execute(
                """
                UPDATE task
                SET title = $2,
                    description = COALESCE($3, description),
                    owner_person_id = COALESCE($4::uuid, owner_person_id),
                    counterpart_person_id = COALESCE($5::uuid, counterpart_person_id),
                    due_at = COALESCE($6, due_at),
                    priority = $7,
                    confidence = $8,
                    evidence = COALESCE($9, evidence),
                    updated_at = now()
                WHERE id = $1::uuid
                """,
                existing_id,
                task.title,
                task.description,
                owner_person_id,
                first_counterpart,
                task.due_at,
                task.priority,
                Decimal(str(task.confidence)),
                "; ".join(task.caveats) if task.caveats else None,
            )
            tasks.append(existing_id)
            continue
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
            task.title,
            task.description,
            owner_person_id,
            first_counterpart,
            chat_id,
            json.dumps(
                {
                    "tg_chat_id": command.tg_chat_id,
                    "tg_message_id": evidence_id,
                    "source_window_id": command.source_window_id,
                }
            ),
            task.due_at,
            task.priority,
            Decimal(str(task.confidence)),
            "; ".join(task.caveats) if task.caveats else None,
        )
        tasks.append(str(row["id"]))
    return tasks


async def _upsert_interaction(
    conn: asyncpg.Connection,
    *,
    chat_id: str,
    participant_ids: list[str],
    task_ids: list[str],
    command: ProjectionCommand,
    source_object_ref: str | None,
) -> str:
    window_start = command.messages[0].occurred_at
    window_end = command.messages[-1].occurred_at
    sentiment = command.features.sentiment_hint
    row = await conn.fetchrow(
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
    if row:
        await conn.execute(
            """
            UPDATE interaction
            SET window_end = $1,
                participants = $2::uuid[],
                topics = $3::text[],
                sentiment = $4,
                summary = $5,
                tasks = $6::uuid[],
                source_object_ref = COALESCE($7, source_object_ref)
            WHERE id = $8::uuid
              AND created_at = $9
            """,
            window_end,
            participant_ids,
            command.result.topics,
            sentiment,
            command.result.summary,
            task_ids,
            source_object_ref,
            row["id"],
            row["created_at"],
        )
        return str(row["id"])

    inserted = await conn.fetchrow(
        """
        INSERT INTO interaction (
            chat_id,
            window_start,
            window_end,
            participants,
            topics,
            sentiment,
            summary,
            tasks,
            source_object_ref
        ) VALUES (
            $1::uuid,
            $2,
            $3,
            $4::uuid[],
            $5::text[],
            $6,
            $7,
            $8::uuid[],
            $9
        )
        RETURNING id
        """,
        chat_id,
        window_start,
        window_end,
        participant_ids,
        command.result.topics,
        sentiment,
        command.result.summary,
        task_ids,
        source_object_ref,
    )
    return str(inserted["id"])


async def _write_artifact(
    s3: S3Client,
    window_id: str,
    command: ProjectionCommand,
) -> str | None:
    if not s3.is_configured:
        return None
    payload = {
        "source_window_id": window_id,
        "tg_chat_id": command.tg_chat_id,
        "messages": [message.model_dump(mode="json") for message in command.messages],
        "features": command.features.model_dump(mode="json"),
        "analysis": command.result.model_dump(mode="json"),
    }
    return await s3.put_raw(
        f"analysis-windows/{window_id}.json",
        json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
    )


async def _write_audit_log(conn: asyncpg.Connection, command: ProjectionCommand) -> None:
    await conn.execute(
        """
        INSERT INTO audit_log (actor, action, target, request_id, payload)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        """,
        "memory-projector",
        "project_analysis",
        command.source_window_id,
        command.trace_id,
        json.dumps(
            {
                "tg_chat_id": command.tg_chat_id,
                "source_event_id": command.source_event_id,
                "topics": command.result.topics,
            },
            ensure_ascii=False,
        ),
    )


async def _project_neo4j(
    driver: Any,
    command: ProjectionCommand,
    participant_map: dict[int, str],
) -> None:
    if not settings.neo4j_password:
        return

    async def _write(tx: Any) -> None:
        await tx.run(
            """
            MERGE (c:Chat {tg_chat_id: $tg_chat_id})
            SET c.kind = $chat_type,
                c.updated_at = datetime()
            """,
            tg_chat_id=command.tg_chat_id,
            chat_type=command.features.chat_type,
        )
        for tg_user_id, person_id in participant_map.items():
            await tx.run(
                """
                MERGE (p:Person {id: $person_id})
                SET p.tg_user_id = $tg_user_id,
                    p.updated_at = datetime()
                MERGE (c:Chat {tg_chat_id: $tg_chat_id})
                MERGE (p)-[:PARTICIPATES_IN]->(c)
                """,
                person_id=person_id,
                tg_user_id=tg_user_id,
                tg_chat_id=command.tg_chat_id,
            )
        for person_a, person_b in combinations(participant_map.values(), 2):
            await tx.run(
                """
                MATCH (a:Person {id: $person_a}), (b:Person {id: $person_b})
                MERGE (a)-[r:COMMUNICATED_WITH]-(b)
                SET r.last_window_id = $window_id,
                    r.last_seen_at = datetime(),
                    r.weight = coalesce(r.weight, 0) + 1
                """,
                person_a=person_a,
                person_b=person_b,
                window_id=command.source_window_id,
            )
        for topic in command.result.topics:
            await tx.run(
                """
                MERGE (t:Topic {slug: $topic})
                SET t.updated_at = datetime()
                WITH t
                MATCH (c:Chat {tg_chat_id: $tg_chat_id})
                MERGE (c)-[:DISCUSSES]->(t)
                """,
                topic=topic,
                tg_chat_id=command.tg_chat_id,
            )
            for person_id in participant_map.values():
                await tx.run(
                    """
                    MATCH (p:Person {id: $person_id})
                    MERGE (t:Topic {slug: $topic})
                    MERGE (p)-[:MENTIONED_TOPIC]->(t)
                    """,
                    person_id=person_id,
                    topic=topic,
                )

    async with driver.session(database=settings.neo4j_database) as session:
        await session.execute_write(_write)


def _build_embedding_job(
    *,
    analysis_window_id: str,
    command: ProjectionCommand,
    participant_ids: list[str],
) -> EmbeddingJob:
    narrative_parts = [command.result.summary]
    if command.result.topics:
        narrative_parts.append("Темы: " + ", ".join(command.result.topics))
    if command.result.claims:
        narrative_parts.append(
            "Факты: " + " ".join(claim.claim for claim in command.result.claims[:6])
        )
    narrative_text = "\n".join(part for part in narrative_parts if part.strip())
    return EmbeddingJob(
        source_window_id=command.source_window_id,
        tg_chat_id=command.tg_chat_id,
        analysis_window_id=analysis_window_id,
        person_ids=participant_ids,
        topic_tags=command.result.topics,
        narrative_text=narrative_text,
        profile_provider=settings.embedding_provider,  # type: ignore[arg-type]
        profile_model=settings.embedding_model,
        profile_alias=settings.embedding_alias,
        trace_id=command.trace_id,
    )


async def _handle_projection(
    command: ProjectionCommand,
    redis: RedisClient,
    s3: S3Client,
    db_pool: asyncpg.Pool,
    neo4j_driver: Any | None,
) -> None:
    async with db_pool.acquire() as conn:
        if await _is_processed(conn, command.command_id):
            return
        async with conn.transaction():
            chat_id = await _ensure_chat(conn, command)
            participant_map = await _ensure_participants(conn, chat_id, command)
            window_id = await _upsert_analysis_window(
                conn,
                chat_id=chat_id,
                participant_map=participant_map,
                command=command,
            )
            await _replace_facts(conn, window_id, command)
            await _replace_signals(conn, window_id, command)
            task_ids = await _sync_tasks(
                conn,
                chat_id=chat_id,
                participant_map=participant_map,
                command=command,
            )
            source_object_ref = await _write_artifact(s3, window_id, command)
            interaction_id = await _upsert_interaction(
                conn,
                chat_id=chat_id,
                participant_ids=list(participant_map.values()),
                task_ids=task_ids,
                command=command,
                source_object_ref=source_object_ref,
            )
            await _write_audit_log(conn, command)
            await _mark_processed(conn, command.command_id)

    if neo4j_driver is not None:
        try:
            await _project_neo4j(neo4j_driver, command, participant_map)
        except Exception as exc:
            log.error("neo4j_projection_failed", source_window_id=command.source_window_id, error=str(exc))

    embedding_job = _build_embedding_job(
        analysis_window_id=window_id,
        command=command,
        participant_ids=list(participant_map.values()),
    )
    await redis.xadd(STREAM_AI_EMBEDDING_REQUESTED, {"data": embedding_job.model_dump_json()})

    interaction_event = InteractionUpdatedEvent(
        interaction_id=interaction_id,
        chat_id=chat_id,
        window_start=command.messages[0].occurred_at,
        window_end=command.messages[-1].occurred_at,
        participants=list(participant_map.values()),
        topics=command.result.topics,
        sentiment=command.features.sentiment_hint,
        summary=command.result.summary,
        task_ids=task_ids,
        trace_id=command.trace_id,
    )
    await redis.xadd(STREAM_INTERACTION_UPDATED, {"data": interaction_event.model_dump_json()})

    log.info(
        "projection_completed",
        source_window_id=command.source_window_id,
        tg_chat_id=command.tg_chat_id,
        participants=len(participant_map),
        claims=len(command.result.claims),
        tasks=len(task_ids),
    )


async def run(
    redis: RedisClient,
    s3: S3Client,
    db_pool: asyncpg.Pool,
    neo4j_driver: Any | None,
) -> None:
    await _ensure_groups(redis)
    while True:
        try:
            entries = await redis.xread_group(
                group=settings.consumer_group,
                consumer=settings.consumer_name,
                streams={settings.stream_projection: ">"},
                count=settings.projection_batch_size,
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
                    command = ProjectionCommand.model_validate_json(str(fields.get("data", "{}")))
                    await _handle_projection(command, redis, s3, db_pool, neo4j_driver)
                except Exception as exc:
                    log.error("projection_error", stream=stream, msg_id=msg_id, error=str(exc))
                finally:
                    await redis.xack(stream, settings.consumer_group, msg_id)


def build_neo4j_driver() -> Any | None:
    if not settings.neo4j_password:
        return None
    return AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
