from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from neo4j import AsyncGraphDatabase
from qdrant_client import AsyncQdrantClient, models

from mcp_rest_api.settings import settings
from pil_contracts import STREAM_AI_REPROCESS_WINDOW, ReprocessWindowCommand
from pil_observability import get_logger
from pil_storage import RedisClient

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

log = get_logger("mcp-rest-api.app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pg_dsn = settings.postgres_dsn.replace("postgresql+asyncpg://", "postgresql://")
    db_pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=8)
    redis = RedisClient(url=settings.redis_url, password=settings.redis_password or None)
    qdrant = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    neo4j_driver = None
    if settings.neo4j_password:
        neo4j_driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        await neo4j_driver.verify_connectivity()

    app.state.db_pool = db_pool
    app.state.redis = redis
    app.state.qdrant = qdrant
    app.state.neo4j_driver = neo4j_driver
    yield
    if neo4j_driver is not None:
        await neo4j_driver.close()
    await qdrant.close()
    await redis.aclose()
    await db_pool.close()


app = FastAPI(title="PIL MCP REST API", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tasks/open")
async def tasks_open(limit: int = 50) -> dict[str, Any]:
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT t.id, t.title, t.description, t.due_at, t.priority, t.confidence,
                   p.display_name AS counterpart_name, c.tg_chat_id
            FROM task t
            LEFT JOIN person p ON p.id = t.counterpart_person_id
            LEFT JOIN chat c ON c.id = t.chat_id
            WHERE t.status = 'open'
            ORDER BY t.due_at NULLS LAST, t.created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return {"items": [dict(row) for row in rows]}


@app.get("/analytics/overview")
async def analytics_overview(days: int = 14) -> dict[str, Any]:
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        summary = await conn.fetchrow(
            """
            SELECT
                count(*)::int AS window_count,
                COALESCE(avg(confidence), 0)::float AS avg_confidence,
                COALESCE(avg((features->>'message_count')::int), 0)::float AS avg_message_count
            FROM analysis_window
            WHERE window_end >= now() - ($1::int * interval '1 day')
            """,
            days,
        )
        signals = await conn.fetch(
            """
            SELECT signal_kind, COALESCE(avg(score), 0)::float AS avg_score, count(*)::int AS samples
            FROM analytics_signal
            WHERE created_at >= now() - ($1::int * interval '1 day')
            GROUP BY signal_kind
            ORDER BY signal_kind
            """,
            days,
        )
        unresolved = await conn.fetchrow(
            """
            SELECT count(*)::int AS open_tasks
            FROM task
            WHERE status = 'open'
            """
        )
    return {
        "window_count": int(summary["window_count"] or 0),
        "avg_confidence": float(summary["avg_confidence"] or 0.0),
        "avg_message_count": float(summary["avg_message_count"] or 0.0),
        "open_tasks": int(unresolved["open_tasks"] or 0),
        "signals": [dict(row) for row in signals],
    }


@app.get("/analytics/conversations")
async def analytics_conversations(limit: int = 20) -> dict[str, Any]:
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                aw.id,
                aw.tg_chat_id,
                aw.window_start,
                aw.window_end,
                aw.summary,
                aw.confidence::float AS confidence,
                aw.features->>'message_count' AS message_count,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'kind', s.signal_kind,
                            'score', s.score::float,
                            'summary', s.summary
                        )
                    ) FILTER (WHERE s.id IS NOT NULL),
                    '[]'::json
                ) AS signals
            FROM analysis_window aw
            LEFT JOIN analytics_signal s ON s.window_id = aw.id
            GROUP BY aw.id
            ORDER BY aw.window_end DESC
            LIMIT $1
            """,
            limit,
        )
    items = []
    for row in rows:
        item = dict(row)
        item["message_count"] = int(item["message_count"] or 0)
        items.append(item)
    return {"items": items}


@app.get("/persons/{person_id}/context")
async def person_context(person_id: str) -> dict[str, Any]:
    pool: asyncpg.Pool = app.state.db_pool
    qdrant: AsyncQdrantClient = app.state.qdrant
    neo4j_driver = app.state.neo4j_driver

    async with pool.acquire() as conn:
        person = await conn.fetchrow(
            """
            SELECT id, tg_user_id, username, display_name, topics, organizations, notes, last_interaction_at
            FROM person
            WHERE id = $1::uuid
            """,
            person_id,
        )
        if person is None:
            raise HTTPException(status_code=404, detail="person_not_found")

        windows = await conn.fetch(
            """
            SELECT aw.id, aw.summary, aw.window_end, aw.analysis_payload
            FROM analysis_window aw
            WHERE EXISTS (
                SELECT 1
                FROM unnest(aw.participant_tg_ids) AS participant_tg_id
                WHERE participant_tg_id = $2
            )
            ORDER BY aw.window_end DESC
            LIMIT 5
            """,
            person_id,
            person["tg_user_id"],
        )

    semantic_hits: list[dict[str, Any]] = []
    try:
        hits, _ = await qdrant.scroll(
            collection_name=settings.qdrant_alias_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="person_ids",
                        match=models.MatchAny(any=[person_id]),
                    )
                ]
            ),
            limit=5,
            with_payload=True,
            with_vectors=False,
        )
        semantic_hits = [point.payload or {} for point in hits]
    except Exception:
        semantic_hits = []

    graph_summary: list[dict[str, Any]] = []
    if neo4j_driver is not None:
        async with neo4j_driver.session(database=settings.neo4j_database) as session:
            records = await session.execute_read(
                lambda tx: tx.run(
                    """
                    MATCH (p:Person {id: $person_id})-[r:COMMUNICATED_WITH]-(other:Person)
                    RETURN other.id AS person_id, coalesce(r.weight, 0) AS weight, r.last_window_id AS last_window_id
                    ORDER BY weight DESC
                    LIMIT 5
                    """,
                    person_id=person_id,
                ).data()
            )
            graph_summary = [dict(record) for record in records]

    return {
        "person": dict(person),
        "recent_windows": [dict(row) for row in windows],
        "semantic_memory": semantic_hits,
        "graph_neighbors": graph_summary,
    }


@app.post("/reprocess/window")
async def reprocess_window(window_id: str) -> dict[str, str]:
    redis: RedisClient = app.state.redis
    command = ReprocessWindowCommand(window_id=window_id)
    await redis.xadd(STREAM_AI_REPROCESS_WINDOW, {"data": command.model_dump_json()})
    return {"status": "queued", "window_id": window_id}


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_ui() -> str:
    overview = await analytics_overview()
    conversations = await analytics_conversations(limit=12)
    signal_rows = "".join(
        f"<tr><td>{signal['signal_kind']}</td><td>{signal['avg_score']:.3f}</td><td>{signal['samples']}</td></tr>"
        for signal in overview["signals"]
    )
    conversation_rows = "".join(
        f"<tr><td>{item['tg_chat_id']}</td><td>{item['message_count']}</td><td>{item['confidence']:.3f}</td><td>{item['summary']}</td></tr>"
        for item in conversations["items"]
    )
    return f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <title>PIL Analytics</title>
        <style>
          body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 32px; background: #f7f4ec; color: #1f2937; }}
          h1, h2 {{ margin-bottom: 12px; }}
          .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 24px; }}
          .card {{ background: white; border-radius: 14px; padding: 16px; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08); }}
          table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 14px; overflow: hidden; }}
          th, td {{ padding: 10px 12px; border-bottom: 1px solid #e5e7eb; text-align: left; vertical-align: top; }}
          th {{ background: #f1efe8; }}
        </style>
      </head>
      <body>
        <h1>Personal Intelligence Analytics</h1>
        <div class="grid">
          <div class="card"><strong>Windows</strong><div>{overview['window_count']}</div></div>
          <div class="card"><strong>Avg confidence</strong><div>{overview['avg_confidence']:.3f}</div></div>
          <div class="card"><strong>Avg messages</strong><div>{overview['avg_message_count']:.2f}</div></div>
          <div class="card"><strong>Open tasks</strong><div>{overview['open_tasks']}</div></div>
        </div>
        <h2>Signals</h2>
        <table>
          <thead><tr><th>Signal</th><th>Average</th><th>Samples</th></tr></thead>
          <tbody>{signal_rows}</tbody>
        </table>
        <h2 style="margin-top: 24px;">Recent conversations</h2>
        <table>
          <thead><tr><th>Chat</th><th>Messages</th><th>Confidence</th><th>Summary</th></tr></thead>
          <tbody>{conversation_rows}</tbody>
        </table>
      </body>
    </html>
    """
