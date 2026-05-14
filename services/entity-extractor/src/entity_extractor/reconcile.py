"""Person reconciliation against Postgres person table."""
import asyncpg
from rapidfuzz import fuzz

_MIN_SIMILARITY = 0.85


async def find_person_id(
    conn: asyncpg.Connection,
    *,
    tg_user_id: int | None = None,
    display_name: str | None = None,
) -> str | None:
    """Return UUID str of matched person, or None."""
    if tg_user_id:
        row = await conn.fetchrow(
            "SELECT id FROM person WHERE tg_user_id = $1 AND NOT blocked",
            tg_user_id,
        )
        if row:
            return str(row["id"])

    if not display_name:
        return None

    rows = await conn.fetch(
        "SELECT id, display_name FROM person WHERE NOT blocked LIMIT 1000"
    )
    best_id: str | None = None
    best_score = 0.0
    needle = display_name.lower()
    for row in rows:
        score = fuzz.ratio(needle, row["display_name"].lower()) / 100.0
        if score > best_score:
            best_score = score
            best_id = str(row["id"])

    return best_id if best_score >= _MIN_SIMILARITY else None


async def upsert_topic(conn: asyncpg.Connection, slug: str, display_name: str) -> str:
    """Insert topic if not exists, return its UUID str."""
    row = await conn.fetchrow(
        """
        INSERT INTO topic (slug, display_name)
        VALUES ($1, $2)
        ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug
        RETURNING id
        """,
        slug,
        display_name,
    )
    return str(row["id"])


async def insert_mention(
    conn: asyncpg.Connection,
    *,
    chat_uuid: str,
    speaker_uuid: str,
    mentioned_uuid: str,
    message_ref: dict,
    context: str | None,
) -> None:
    await conn.execute(
        """
        INSERT INTO mention (chat_id, speaker_person_id, mentioned_person_id, message_ref, context)
        VALUES ($1::uuid, $2::uuid, $3::uuid, $4::jsonb, $5)
        """,
        chat_uuid,
        speaker_uuid,
        mentioned_uuid,
        __import__("json").dumps(message_ref),
        context,
    )
