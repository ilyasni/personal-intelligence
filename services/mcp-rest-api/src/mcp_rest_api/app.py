from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import asyncpg
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from neo4j import AsyncGraphDatabase
from qdrant_client import AsyncQdrantClient, models

from mcp_rest_api.settings import settings
from pil_contracts import STREAM_AI_REPROCESS_WINDOW, ReprocessWindowCommand
from pil_storage import RedisClient

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence
    from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
router = APIRouter()


def _format_datetime(value: datetime | str | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    return value.strftime("%Y-%m-%d %H:%M")


def _join_values(values: Sequence[str] | None) -> str:
    if not values:
        return "—"
    cleaned = [value for value in values if value]
    return ", ".join(cleaned) if cleaned else "—"


def _bool_label(value: bool) -> str:
    return "yes" if value else "no"


templates.env.filters["datetime"] = _format_datetime
templates.env.filters["csvish"] = _join_values
templates.env.filters["bool_label"] = _bool_label


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


def _template_context(
    request: Request,
    *,
    page_title: str,
    current_page: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "request": request,
        "page_title": page_title,
        "current_page": current_page,
        "static_path": str(request.url_for("static", path="admin.css")),
        **extra,
    }


async def get_open_tasks_data(app: FastAPI, limit: int = 50) -> list[dict[str, Any]]:
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT t.id, t.title, t.description, t.due_at, t.priority, t.confidence::float AS confidence,
                   t.status, p.display_name AS counterpart_name, c.tg_chat_id
            FROM task t
            LEFT JOIN person p ON p.id = t.counterpart_person_id
            LEFT JOIN chat c ON c.id = t.chat_id
            WHERE t.status = 'open'
            ORDER BY t.due_at NULLS LAST, t.created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(row) for row in rows]


async def get_analytics_overview_data(app: FastAPI, days: int = 14) -> dict[str, Any]:
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
        people = await conn.fetchrow("SELECT count(*)::int AS people_count FROM person")
        chats = await conn.fetchrow("SELECT count(*)::int AS chat_count FROM chat")
    return {
        "window_count": int(summary["window_count"] or 0),
        "avg_confidence": float(summary["avg_confidence"] or 0.0),
        "avg_message_count": float(summary["avg_message_count"] or 0.0),
        "open_tasks": int(unresolved["open_tasks"] or 0),
        "people_count": int(people["people_count"] or 0),
        "chat_count": int(chats["chat_count"] or 0),
        "signals": [dict(row) for row in signals],
    }


async def get_conversation_data(app: FastAPI, limit: int = 20) -> list[dict[str, Any]]:
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
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["message_count"] = int(item["message_count"] or 0)
        items.append(item)
    return items


async def get_people_data(app: FastAPI, limit: int = 50) -> list[dict[str, Any]]:
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                id,
                tg_user_id,
                username,
                display_name,
                organizations,
                topics,
                communication_style,
                trust_score::float AS trust_score,
                last_interaction_at,
                blocked
            FROM person
            ORDER BY COALESCE(last_interaction_at, updated_at) DESC NULLS LAST, created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(row) for row in rows]


async def get_chat_data(app: FastAPI, limit: int = 50) -> list[dict[str, Any]]:
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.id,
                c.tg_chat_id,
                c.kind,
                c.title,
                c.is_allowed,
                c.member_count,
                count(aw.id)::int AS window_count,
                max(aw.window_end) AS last_window_end
            FROM chat c
            LEFT JOIN analysis_window aw ON aw.chat_id = c.id
            GROUP BY c.id
            ORDER BY max(aw.window_end) DESC NULLS LAST, c.updated_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(row) for row in rows]


async def get_person_context_data(app: FastAPI, person_id: str) -> dict[str, Any]:
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


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/tasks/open")
async def tasks_open(request: Request, limit: int = 50) -> dict[str, Any]:
    return {"items": await get_open_tasks_data(request.app, limit=limit)}


@router.get("/analytics/overview")
async def analytics_overview(request: Request, days: int = 14) -> dict[str, Any]:
    return await get_analytics_overview_data(request.app, days=days)


@router.get("/analytics/conversations")
async def analytics_conversations(request: Request, limit: int = 20) -> dict[str, Any]:
    return {"items": await get_conversation_data(request.app, limit=limit)}


@router.get("/persons/{person_id}/context")
async def person_context(request: Request, person_id: str) -> dict[str, Any]:
    return await get_person_context_data(request.app, person_id)


@router.post("/reprocess/window")
async def reprocess_window(request: Request, window_id: str) -> dict[str, str]:
    redis: RedisClient = request.app.state.redis
    command = ReprocessWindowCommand(window_id=window_id)
    await redis.xadd(STREAM_AI_REPROCESS_WINDOW, {"data": command.model_dump_json()})
    return {"status": "queued", "window_id": window_id}


@router.get("/analytics", response_class=HTMLResponse, include_in_schema=False)
async def analytics_ui_alias() -> RedirectResponse:
    return RedirectResponse(url="/admin", status_code=307)


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_overview(request: Request) -> HTMLResponse:
    overview, conversations, tasks, people, chats = await asyncio.gather(
        get_analytics_overview_data(request.app),
        get_conversation_data(request.app, limit=6),
        get_open_tasks_data(request.app, limit=6),
        get_people_data(request.app, limit=6),
        get_chat_data(request.app, limit=6),
    )
    return templates.TemplateResponse(
        request=request,
        name="admin_overview.html",
        context=_template_context(
            request,
            page_title="Control Room",
            current_page="overview",
            overview=overview,
            conversations=conversations,
            tasks=tasks,
            people=people,
            chats=chats,
        ),
    )


@router.get("/admin/conversations", response_class=HTMLResponse, include_in_schema=False)
async def admin_conversations(request: Request, limit: int = 25) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="admin_conversations.html",
        context=_template_context(
            request,
            page_title="Conversations",
            current_page="conversations",
            conversations=await get_conversation_data(request.app, limit=limit),
            limit=limit,
        ),
    )


@router.get("/admin/tasks", response_class=HTMLResponse, include_in_schema=False)
async def admin_tasks(request: Request, limit: int = 50) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="admin_tasks.html",
        context=_template_context(
            request,
            page_title="Tasks",
            current_page="tasks",
            tasks=await get_open_tasks_data(request.app, limit=limit),
            limit=limit,
        ),
    )


@router.get("/admin/people", response_class=HTMLResponse, include_in_schema=False)
async def admin_people(request: Request, limit: int = 50) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="admin_people.html",
        context=_template_context(
            request,
            page_title="People",
            current_page="people",
            people=await get_people_data(request.app, limit=limit),
            limit=limit,
        ),
    )


@router.get("/admin/chats", response_class=HTMLResponse, include_in_schema=False)
async def admin_chats(request: Request, limit: int = 50) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="admin_chats.html",
        context=_template_context(
            request,
            page_title="Chats",
            current_page="chats",
            chats=await get_chat_data(request.app, limit=limit),
            limit=limit,
        ),
    )


def create_app(*, use_lifespan: bool = True) -> FastAPI:
    app = FastAPI(
        title="PIL MCP REST API",
        version="0.1.0",
        lifespan=lifespan if use_lifespan else None,
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(router)
    return app


app = create_app()
