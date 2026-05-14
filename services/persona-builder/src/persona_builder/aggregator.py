"""Aggregate EntityFoundEvent data into person profile updates."""
import math
from datetime import datetime, timezone

import asyncpg

from persona_builder.settings import settings


async def update_person_from_event(
    conn: asyncpg.Connection,
    *,
    tg_sender_id: int | None,
    tg_chat_id: int,
    organizations: list[str],
    topics: list[str],
    occurred_at: datetime,
) -> str | None:
    """Merge new org/topic candidates into sender's person row. Returns person UUID or None."""
    if not tg_sender_id:
        return None

    row = await conn.fetchrow(
        "SELECT id, organizations, topics FROM person WHERE tg_user_id = $1 AND NOT blocked",
        tg_sender_id,
    )
    if not row:
        return None

    person_id = str(row["id"])
    existing_orgs: list[str] = list(row["organizations"] or [])
    existing_topics: list[str] = list(row["topics"] or [])

    merged_orgs = _merge_list(existing_orgs, organizations, settings.persona_max_organizations)
    merged_topics = _merge_list(existing_topics, topics, settings.persona_max_topics)

    trust = await _compute_trust(conn, person_id, occurred_at)

    await conn.execute(
        """
        UPDATE person SET
            organizations = $1,
            topics = $2,
            trust_score = $3,
            last_interaction_at = $4,
            updated_at = now()
        WHERE id = $5::uuid
        """,
        merged_orgs,
        merged_topics,
        trust,
        occurred_at,
        person_id,
    )

    return person_id


def _merge_list(existing: list[str], new: list[str], max_len: int) -> list[str]:
    """Append new items to existing, dedup, cap at max_len."""
    seen = set(existing)
    merged = list(existing)
    for item in new:
        norm = item.lower().strip()
        if norm and norm not in seen:
            seen.add(norm)
            merged.append(norm)
    return merged[-max_len:]


async def _compute_trust(
    conn: asyncpg.Connection,
    person_id: str,
    now: datetime,
) -> float:
    """Simplified MVP-1 trust formula."""
    row = await conn.fetchrow(
        """
        SELECT
            last_interaction_at,
            (SELECT COUNT(*) FROM mention
             WHERE (speaker_person_id = $1::uuid OR mentioned_person_id = $1::uuid)
               AND created_at >= now() - interval '30 days') AS mention_count_30d
        FROM person WHERE id = $1::uuid
        """,
        person_id,
    )
    if not row:
        return 0.5

    last_at: datetime | None = row["last_interaction_at"]
    mention_count = int(row["mention_count_30d"] or 0)

    if last_at is None:
        recency = 0.0
    else:
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        days_since = (now - last_at).total_seconds() / 86400
        recency = math.exp(-days_since / 30)

    frequency = math.log1p(mention_count) / math.log1p(200)

    trust = 0.5 * recency + 0.3 * frequency + 0.2 * 0.5  # consistency=0.5 placeholder
    return round(min(0.95, max(0.05, trust)), 3)
