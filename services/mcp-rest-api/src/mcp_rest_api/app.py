from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, cast
from urllib.parse import quote

import asyncpg
from fastapi import APIRouter, BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from neo4j import AsyncGraphDatabase
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient, models

from mcp_rest_api.settings import settings
from pil_contracts import STREAM_AI_REPROCESS_WINDOW, ReprocessWindowCommand
from pil_llm import OpenAICompatChatClient, SummaryPayload, WormsoftConfig, build_wormsoft_client
from pil_storage import RedisClient, S3Client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence
    from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
PERSON_DETAIL_QDRANT_TIMEOUT_S = 0.8
PERSON_DETAIL_NEO4J_TIMEOUT_S = 0.8

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
router = APIRouter()
STATIC_ASSET_VERSION = str(int((STATIC_DIR / "admin.css").stat().st_mtime))


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
    return "да" if value else "нет"


def _status_label(value: str | None) -> str:
    mapping = {
        "open": "открыта",
        "done": "выполнена",
        "dropped": "отклонена",
    }
    if value is None:
        return "—"
    return mapping.get(value, value)


def _chat_kind_label(value: str | None) -> str:
    mapping = {
        "private": "личный",
        "group": "группа",
        "supergroup": "супергруппа",
        "channel": "канал",
    }
    if value is None:
        return "—"
    return mapping.get(value, value)


def _pretty_json(value: Any) -> str:
    if value is None:
        return "{}"
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value else []
        value = decoded
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _parse_manual_tags(value: str | None) -> list[str]:
    if not value:
        return []
    normalized_tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in re.split(r"[,;\n]", value):
        tag = " ".join(raw_tag.strip().split()).casefold()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        normalized_tags.append(tag)
    return normalized_tags


def _list_preview(values: Sequence[str] | None, *, limit: int) -> tuple[list[str], int]:
    cleaned = [value for value in values or [] if value]
    if len(cleaned) <= limit:
        return cleaned, 0
    return cleaned[:limit], len(cleaned) - limit


def _truncate_text(value: str | None, *, limit: int = 240) -> str:
    if not value:
        return "—"
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def _semantic_memory_preview_items(items: Sequence[dict[str, Any]] | None) -> list[dict[str, Any]]:
    previews: list[dict[str, Any]] = []
    for item in items or []:
        kind = str(item.get("kind") or item.get("type") or "memory")
        summary_source = item.get("summary") or item.get("narrative") or item.get("text") or item.get("content")
        previews.append(
            {
                "kind": kind,
                "summary": _truncate_text(str(summary_source) if summary_source is not None else None, limit=220),
                "window_id": item.get("window_id"),
                "chat_id": item.get("tg_chat_id"),
            }
        )
    return previews


async def _await_with_timeout(
    awaitable: Any,
    *,
    timeout_s: float,
    fallback: Any,
    status_name: str,
) -> tuple[Any, str]:
    try:
        async with asyncio.timeout(timeout_s):
            return await awaitable, "ok"
    except TimeoutError:
        return fallback, f"{status_name}_timeout"
    except Exception:
        return fallback, f"{status_name}_error"


class PersonAnnotationsForm(BaseModel):
    manual_tags: str = ""
    notes: str = ""
    redirect_to: str = "/admin/people"

    model_config = {"extra": "forbid"}


class OwnerProfileForm(BaseModel):
    context_tags: str = ""
    profile_notes: str = ""
    preferred_language: str = "ru"

    model_config = {"extra": "forbid"}


class RelationshipAnnotationForm(BaseModel):
    relationship_labels: str = ""
    relationship_note: str = ""
    redirect_to: str = "/admin/people"

    model_config = {"extra": "forbid"}


def _normalize_preferred_language(value: str | None) -> str:
    normalized = (value or "").strip().casefold()
    return normalized if normalized in {"ru", "en"} else "ru"


FLASH_MESSAGES = {
    "window_requeued": ("success", "Окно добавлено в очередь на повторную обработку."),
    "task_status_done": ("success", "Задача переведена в статус «выполнено»."),
    "task_status_open": ("success", "Задача снова открыта."),
    "task_status_dropped": ("warn", "Задача переведена в статус «отклонено»."),
    "chat_allowed": ("success", "Чат добавлен в allowlist."),
    "chat_disallowed": ("warn", "Чат удалён из allowlist."),
    "person_blocked": ("warn", "Профиль заблокирован для ingestion и дальнейшей обработки."),
    "person_unblocked": ("success", "Профиль разблокирован и снова участвует в обработке."),
    "person_annotations_saved": ("success", "Теги и комментарий сохранены."),
    "owner_profile_saved": ("success", "Контекст владельца сохранён."),
    "relationship_annotation_saved": ("success", "Контекст отношений сохранён."),
    "owner_profile_readonly": ("info", "Профиль владельца вынесен в отдельный first-party раздел и не редактируется как обычная персона."),
    "person_erased": ("success", "Профиль удалён из канонической памяти и выведен из админки."),
    "person_erased_with_warnings": ("warn", "Профиль удалён, но часть производных следов потребует дополнительной дочистки."),
}


templates.env.filters["datetime"] = _format_datetime
templates.env.filters["csvish"] = _join_values
templates.env.filters["bool_label"] = _bool_label
templates.env.filters["status_label"] = _status_label
templates.env.filters["chat_kind_label"] = _chat_kind_label
templates.env.filters["prettyjson"] = _pretty_json


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pg_dsn = settings.postgres_dsn.replace("postgresql+asyncpg://", "postgresql://")
    db_pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=8)
    redis = RedisClient(url=settings.redis_url, password=settings.redis_password or None)
    qdrant = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    s3 = S3Client(
        endpoint_url=settings.s3_endpoint_url,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
        region=settings.s3_region,
        bucket_raw=settings.s3_bucket_raw,
        bucket_media=settings.s3_bucket_media,
    )
    grounded_llm = build_wormsoft_client(
        WormsoftConfig(
            api_base=settings.wormsoft_api_base,
            api_key=settings.wormsoft_api_key,
            model=settings.wormsoft_model_default,
            max_parallel_requests=settings.wormsoft_max_simultaneous_requests,
            min_request_interval_ms=settings.wormsoft_min_request_interval_ms,
            max_retries=settings.wormsoft_max_retries,
        ),
        service_name="mcp-rest-api-wormsoft",
    )
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
    app.state.s3 = s3
    app.state.grounded_llm = grounded_llm
    app.state.neo4j_driver = neo4j_driver
    app.state.jobs = {}
    yield
    if neo4j_driver is not None:
        await neo4j_driver.close()
    await grounded_llm.close()
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
        "static_path": f"{request.url_for('static', path='admin.css')}?v={STATIC_ASSET_VERSION}",
        "flash": _get_flash_message(request),
        **extra,
    }


def _get_flash_message(request: Request) -> dict[str, str] | None:
    key = request.query_params.get("flash")
    if not key:
        return None
    level, text = FLASH_MESSAGES.get(key, ("info", "Действие выполнено."))
    return {"level": level, "text": text}


def _redirect_with_flash(path: str, flash_key: str) -> RedirectResponse:
    separator = "&" if "?" in path else "?"
    response = RedirectResponse(url=f"{path}{separator}flash={quote(flash_key)}", status_code=303)
    _apply_admin_no_cache_headers(response)
    return response


def _apply_admin_no_cache_headers(response: HTMLResponse | RedirectResponse) -> None:
    # HTML/redirect responses for admin pages should not land in shared proxy/CDN caches.
    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0, private"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    # Некоторые CDN (Fastly и др.) смотрят Surrogate-Control, если игнорируют общий Cache-Control.
    response.headers["Surrogate-Control"] = "no-store"


def _admin_template_response(
    request: Request,
    *,
    name: str,
    context: dict[str, Any],
) -> HTMLResponse:
    response = templates.TemplateResponse(
        request=request,
        name=name,
        context=context,
    )
    _apply_admin_no_cache_headers(response)
    return response


def _hash_identifier(raw_id: str) -> str:
    return hashlib.sha256(raw_id.encode("utf-8")).hexdigest()


def _rowcount_from_execute(result: str) -> int:
    try:
        return int(result.rsplit(" ", maxsplit=1)[-1])
    except (ValueError, IndexError):
        return 0


async def _write_audit_entry(
    app: FastAPI,
    *,
    actor: str,
    action: str,
    target: str,
    payload: dict[str, Any],
) -> None:
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO audit_log (actor, action, target, payload)
            VALUES ($1, $2, $3, $4::jsonb)
            """,
            actor,
            action,
            target,
            json.dumps(payload, ensure_ascii=False, default=str),
        )


async def _validate_person_erase_target(app: FastAPI, person_id: str) -> dict[str, Any]:
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        person = await conn.fetchrow(
            """
            SELECT id, display_name, tg_user_id, is_owner
            FROM person
            WHERE id = $1::uuid
            """,
            person_id,
        )
        if person is None:
            raise HTTPException(status_code=404, detail="person_not_found")
        owner_backing = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1
                FROM owner_profile
                WHERE backing_person_id = $1::uuid
            )
            """,
            person_id,
        )
    if bool(person["is_owner"]) or bool(owner_backing):
        raise HTTPException(status_code=400, detail="owner_profile_cannot_be_erased")
    return dict(person)


async def erase_person_cascade(
    app: FastAPI,
    person_id: str,
    *,
    actor: str,
) -> dict[str, Any]:
    person = await _validate_person_erase_target(app, person_id)
    pool: asyncpg.Pool = app.state.db_pool
    qdrant: AsyncQdrantClient = app.state.qdrant
    s3: S3Client = app.state.s3
    neo4j_driver = app.state.neo4j_driver
    hashed_target = _hash_identifier(person_id)
    warnings: list[str] = []

    async with pool.acquire() as conn, conn.transaction():
        relationship_count = await conn.fetchval(
            """
            SELECT count(*)::int
            FROM relationship_annotation
            WHERE person_id = $1::uuid
            """,
            person_id,
        ) or 0
        membership_count = await conn.fetchval(
            """
            SELECT count(*)::int
            FROM chat_membership
            WHERE person_id = $1::uuid
            """,
            person_id,
        ) or 0
        mention_count = await conn.fetchval(
            """
            SELECT count(*)::int
            FROM mention
            WHERE speaker_person_id = $1::uuid
               OR mentioned_person_id = $1::uuid
            """,
            person_id,
        ) or 0
        task_rows = await conn.fetch(
            """
            SELECT id
            FROM task
            WHERE owner_person_id = $1::uuid
               OR counterpart_person_id = $1::uuid
            """,
            person_id,
        )
        interaction_rows = await conn.fetch(
            """
            SELECT id, source_object_ref
            FROM interaction
            WHERE $1::uuid = ANY(participants)
            """,
            person_id,
        )
        window_rows: list[asyncpg.Record] = []
        tg_user_id = person.get("tg_user_id")
        if tg_user_id is not None:
            window_rows = await conn.fetch(
                """
                SELECT id
                FROM analysis_window
                WHERE $1::bigint = ANY(participant_tg_ids)
                """,
                tg_user_id,
            )

        task_ids = [row["id"] for row in task_rows]
        interaction_ids = [row["id"] for row in interaction_rows]
        analysis_window_ids = [row["id"] for row in window_rows]
        source_object_refs = [
            str(row["source_object_ref"])
            for row in interaction_rows
            if row["source_object_ref"] is not None and str(row["source_object_ref"])
        ]

        deleted_analytics_signals = 0
        deleted_extracted_facts = 0
        deleted_analysis_windows = 0
        if analysis_window_ids:
            deleted_analytics_signals = _rowcount_from_execute(
                await conn.execute(
                    """
                    DELETE FROM analytics_signal
                    WHERE window_id = ANY($1::uuid[])
                    """,
                    analysis_window_ids,
                )
            )
            deleted_extracted_facts = _rowcount_from_execute(
                await conn.execute(
                    """
                    DELETE FROM extracted_fact
                    WHERE window_id = ANY($1::uuid[])
                    """,
                    analysis_window_ids,
                )
            )
            deleted_analysis_windows = _rowcount_from_execute(
                await conn.execute(
                    """
                    DELETE FROM analysis_window
                    WHERE id = ANY($1::uuid[])
                    """,
                    analysis_window_ids,
                )
            )

        deleted_interactions = 0
        if interaction_ids:
            deleted_interactions = _rowcount_from_execute(
                await conn.execute(
                    """
                    DELETE FROM interaction
                    WHERE id = ANY($1::uuid[])
                    """,
                    interaction_ids,
                )
            )

        deleted_tasks = 0
        if task_ids:
            deleted_tasks = _rowcount_from_execute(
                await conn.execute(
                    """
                    DELETE FROM task
                    WHERE id = ANY($1::uuid[])
                    """,
                    task_ids,
                )
            )

        deleted_people = _rowcount_from_execute(
            await conn.execute(
                """
                DELETE FROM person
                WHERE id = $1::uuid
                """,
                person_id,
            )
        )
        if deleted_people == 0:
            raise HTTPException(status_code=404, detail="person_not_found")

    try:
        await qdrant.delete(
            collection_name=settings.qdrant_alias_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="person_ids",
                            match=models.MatchAny(any=[person_id]),
                        )
                    ]
                )
            ),
            wait=True,
        )
    except Exception:
        warnings.append("qdrant_cleanup_failed")

    if neo4j_driver is not None:
        try:
            async with neo4j_driver.session(database=settings.neo4j_database) as session:
                await session.run("MATCH (p:Person {id: $person_id}) DETACH DELETE p", person_id=person_id)
        except Exception:
            warnings.append("neo4j_cleanup_failed")

    deleted_object_refs = 0
    if source_object_refs:
        if s3.is_configured:
            for source_object_ref in source_object_refs:
                try:
                    await s3.delete_bucket_object(s3.bucket_raw, source_object_ref)
                    deleted_object_refs += 1
                except Exception:
                    warnings.append("s3_cleanup_failed")
                    break
        else:
            warnings.append("s3_not_configured")

    summary = {
        "person_id": person_id,
        "display_name": person.get("display_name"),
        "target_hash": hashed_target,
        "deleted": {
            "person": deleted_people,
            "relationship_annotations": int(relationship_count),
            "memberships": int(membership_count),
            "mentions": int(mention_count),
            "tasks": int(deleted_tasks),
            "analysis_windows": int(deleted_analysis_windows),
            "analytics_signals": int(deleted_analytics_signals),
            "extracted_facts": int(deleted_extracted_facts),
            "interactions": int(deleted_interactions),
            "interaction_artifacts": int(deleted_object_refs),
        },
        "warnings": warnings,
    }
    await _write_audit_entry(
        app,
        actor=actor,
        action="system.erase.person",
        target=hashed_target,
        payload=summary,
    )
    return summary


async def _run_person_erase_job(app: FastAPI, job_id: str, person_id: str) -> None:
    jobs: dict[str, dict[str, Any]] = app.state.jobs
    jobs[job_id] = {"job_id": job_id, "person_id": person_id, "status": "running"}
    try:
        result = await erase_person_cascade(app, person_id, actor="system")
    except HTTPException as exc:
        jobs[job_id] = {
            "job_id": job_id,
            "person_id": person_id,
            "status": "failed",
            "error": exc.detail,
        }
        return
    except Exception as exc:
        jobs[job_id] = {
            "job_id": job_id,
            "person_id": person_id,
            "status": "failed",
            "error": str(exc),
        }
        return
    jobs[job_id] = {
        "job_id": job_id,
        "person_id": person_id,
        "status": "done",
        "result": result,
    }


def _person_brief_heuristic(detail: dict[str, Any]) -> SummaryPayload:
    person = detail["person"]
    relationship = detail.get("relationship_annotation", {})
    task_titles = [str(task.get("title") or "").strip() for task in detail.get("tasks", []) if task.get("title")]
    recent_windows = [window for window in detail.get("recent_windows", []) if window.get("summary")]
    labels = _normalize_string_list(relationship.get("labels"))
    parts = [f"{person.get('display_name') or 'Контакт'} — внешний контакт владельца."]
    if labels:
        parts.append(f"Основной контекст: {', '.join(labels)}.")
    if recent_windows:
        parts.append(
            f"В последних окнах чаще всего всплывают темы: {recent_windows[0].get('summary')}."  # noqa: RUF001
        )
    if task_titles:
        parts.append(f"С ним сейчас связаны задачи: {', '.join(task_titles[:3])}.")  # noqa: RUF001
    if not recent_windows and not task_titles:
        parts.append("Недостаточно данных для доказательного краткого профиля.")
    return SummaryPayload(
        summary=" ".join(parts),
        tasks=task_titles[:5],
        topics=_normalize_string_list(person.get("topics"))[:5],
    )


def _brief_confidence(detail: dict[str, Any], *, provider: str, evidence_count: int) -> float:
    score = 0.38
    if detail.get("relationship_annotation", {}).get("labels"):
        score += 0.08
    if detail.get("tasks"):
        score += 0.08
    score += min(len(detail.get("recent_windows", [])), 3) * 0.08
    score += min(evidence_count, 6) * 0.02
    if provider == "wormsoft":
        score += 0.08
    return round(min(score, 0.86), 3)


async def synthesize_person_brief(app: FastAPI, person_id: str) -> dict[str, Any]:
    detail = await get_person_detail_data(app, person_id)
    if detail["person"].get("is_owner"):
        raise HTTPException(status_code=400, detail="owner_profile_brief_not_supported")

    person = detail["person"]
    relationship = detail.get("relationship_annotation", {})
    recent_windows = detail.get("recent_windows", [])
    task_titles = [str(task.get("title") or "").strip() for task in detail.get("tasks", []) if task.get("title")]
    evidence_window_ids = [str(window.get("id")) for window in recent_windows[:3] if window.get("id")]
    evidence_message_ids: list[int] = []
    for window in recent_windows[:3]:
        for message_id in window.get("source_message_ids") or []:
            if isinstance(message_id, int) and message_id not in evidence_message_ids:
                evidence_message_ids.append(message_id)

    llm_client: OpenAICompatChatClient = app.state.grounded_llm
    provider = "heuristic"
    caveats: list[str] = []
    if len(recent_windows) <= 1:
        caveats.append("single-window evidence")
    if not evidence_message_ids:
        caveats.append("insufficient context")

    heuristic_payload = _person_brief_heuristic(detail)
    payload = heuristic_payload
    if llm_client.is_available:
        provider = "wormsoft"
        system_prompt = (
            "Ты готовишь очень короткий evidence-backed brief по человеку для личной memory-system. "
            "Пиши только по-русски. Не выдумывай факты, не делай психодиагностику, не делай клинических выводов. "  # noqa: RUF001
            "Опирайся только на переданный контекст. Верни JSON с полями summary, topics, tasks, sentiment."  # noqa: RUF001
        )
        user_prompt = "\n".join(
            [
                f"Имя: {person.get('display_name') or '—'}",
                f"Username: @{person.get('username') or 'не указан'}",
                f"Контекст отношений: {', '.join(_normalize_string_list(relationship.get('labels'))) or 'не указан'}",
                f"Заметка об отношениях: {relationship.get('note') or '—'}",  # noqa: RUF001
                f"Темы: {', '.join(_normalize_string_list(person.get('topics'))) or '—'}",
                f"Организации: {', '.join(_normalize_string_list(person.get('organizations'))) or '—'}",
                f"Задачи: {', '.join(task_titles[:5]) or '—'}",
                "Последние окна:",
                *[
                    f"- {window.get('window_end')}: {window.get('summary')}"
                    for window in recent_windows[:3]
                ],
                "Сделай 2-4 предложения. Если данных мало, прямо скажи об этом.",  # noqa: RUF001
            ]
        )
        try:
            payload = await llm_client.complete_summary(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model_override=settings.wormsoft_model_default,
                max_tokens=280,
                max_summary_chars=420,
                max_tasks=5,
            )
            summary_text = str(payload.summary or "").strip()
            if (
                not summary_text
                or summary_text == "No summary generated."
                or summary_text.startswith("{")
                or summary_text.startswith("```")
            ):
                payload = heuristic_payload
                provider = "heuristic"
                caveats.append("llm payload invalid")
        except Exception:
            provider = "heuristic"
            caveats.append("heuristic fallback")

    if provider == "heuristic" and "heuristic fallback" not in caveats:
        caveats.append("heuristic fallback")

    confidence = _brief_confidence(detail, provider=provider, evidence_count=len(evidence_message_ids))
    return {
        "person_id": person_id,
        "display_name": person.get("display_name"),
        "provider": provider,
        "summary": payload.summary,
        "topics": payload.topics,
        "task_titles": payload.tasks or task_titles[:5],
        "confidence": confidence,
        "evidence_window_ids": evidence_window_ids,
        "evidence_message_ids": evidence_message_ids[:8],
        "caveats": caveats,
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
        people = await conn.fetchrow(
            """
            SELECT
                (SELECT count(*)::int FROM person WHERE is_owner = FALSE) AS people_count,
                (SELECT count(*)::int FROM owner_profile) AS owner_profile_count
            """
        )
        chats = await conn.fetchrow("SELECT count(*)::int AS chat_count FROM chat")
    return {
        "window_count": int(summary["window_count"] or 0),
        "avg_confidence": float(summary["avg_confidence"] or 0.0),
        "avg_message_count": float(summary["avg_message_count"] or 0.0),
        "open_tasks": int(unresolved["open_tasks"] or 0),
        "people_count": int(people["people_count"] or 0),
        "owner_profile_count": int(people["owner_profile_count"] or 0),
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
        raw_signals = item.get("signals")
        if isinstance(raw_signals, str):
            try:
                raw_signals = json.loads(raw_signals)
            except json.JSONDecodeError:
                raw_signals = []
        if not isinstance(raw_signals, list):
            raw_signals = []
        item["signals"] = [signal for signal in raw_signals if isinstance(signal, dict)]
        items.append(item)
    return items


async def get_people_data(
    app: FastAPI,
    limit: int = 50,
    *,
    manual_tag: str | None = None,
    relationship_label: str | None = None,
    include_owner: bool = False,
) -> list[dict[str, Any]]:
    pool: asyncpg.Pool = app.state.db_pool
    normalized_manual_tag = _normalize_optional_text(manual_tag)
    normalized_relationship_label = _normalize_optional_text(relationship_label)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH current_owner AS (
                SELECT id
                FROM owner_profile
                ORDER BY updated_at DESC
                LIMIT 1
            )
            SELECT
                p.id,
                p.tg_user_id,
                p.username,
                p.display_name,
                p.organizations,
                p.topics,
                p.manual_tags,
                p.communication_style,
                p.trust_score::float AS trust_score,
                p.last_interaction_at,
                p.blocked,
                p.is_owner,
                COALESCE(ra.labels, ARRAY[]::text[]) AS relationship_labels,
                ra.note AS relationship_note
            FROM person p
            LEFT JOIN current_owner owner ON TRUE
            LEFT JOIN relationship_annotation ra
              ON ra.owner_profile_id = owner.id
             AND ra.person_id = p.id
            WHERE ($2::text IS NULL OR $2 = ANY(p.manual_tags))
              AND ($3::text IS NULL OR $3 = ANY(COALESCE(ra.labels, ARRAY[]::text[])))
              AND ($4::bool OR p.is_owner = FALSE)
            ORDER BY COALESCE(p.last_interaction_at, p.updated_at) DESC NULLS LAST, p.created_at DESC
            LIMIT $1
            """,
            limit,
            normalized_manual_tag,
            normalized_relationship_label,
            include_owner,
        )
    items = [dict(row) for row in rows]
    for item in items:
        item["organizations"] = _normalize_string_list(item.get("organizations"))
        item["topics"] = _normalize_string_list(item.get("topics"))
        item["manual_tags"] = _normalize_string_list(item.get("manual_tags"))
        item["relationship_labels"] = _normalize_string_list(item.get("relationship_labels"))
    return items


async def get_owner_person_id(app: FastAPI) -> str:
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        owner_profile_row = await conn.fetchrow(
            """
            SELECT backing_person_id
            FROM owner_profile
            WHERE backing_person_id IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
            """
        )
        if owner_profile_row is not None and owner_profile_row["backing_person_id"] is not None:
            return str(owner_profile_row["backing_person_id"])
        row = await conn.fetchrow(
            """
            SELECT id
            FROM person
            WHERE is_owner = TRUE
            ORDER BY updated_at DESC
            LIMIT 1
            """
        )
    if row is None:
        raise HTTPException(status_code=404, detail="owner_profile_not_found")
    return str(row["id"])


async def get_owner_profile_record(app: FastAPI) -> dict[str, Any] | None:
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                id,
                backing_person_id,
                tg_user_id,
                username,
                display_name,
                preferred_language,
                context_tags,
                profile_notes,
                last_interaction_at,
                created_at,
                updated_at
            FROM owner_profile
            ORDER BY updated_at DESC
            LIMIT 1
            """
        )
    if row is None:
        return None
    item = dict(row)
    item["context_tags"] = _normalize_string_list(item.get("context_tags"))
    item["context_tags_preview"], item["context_tags_hidden_count"] = _list_preview(
        item["context_tags"],
        limit=8,
    )
    item["preferred_language"] = _normalize_preferred_language(cast("str | None", item.get("preferred_language")))
    return item


async def get_current_owner_profile_id(app: FastAPI) -> str:
    owner_profile = await get_owner_profile_record(app)
    if owner_profile is None or owner_profile.get("id") is None:
        raise HTTPException(status_code=404, detail="owner_profile_not_found")
    return str(owner_profile["id"])


async def get_chat_data(app: FastAPI, limit: int = 50) -> list[dict[str, Any]]:
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH current_owner AS (
                SELECT id
                FROM owner_profile
                ORDER BY updated_at DESC
                LIMIT 1
            )
            SELECT
                c.id,
                c.tg_chat_id,
                c.kind,
                c.title,
                c.is_allowed,
                c.member_count,
                count(aw.id)::int AS window_count,
                max(aw.window_end) AS last_window_end,
                COALESCE(ra.labels, ARRAY[]::text[]) AS relationship_labels,
                ra.note AS relationship_note
            FROM chat c
            LEFT JOIN current_owner owner ON TRUE
            LEFT JOIN relationship_annotation ra
              ON ra.owner_profile_id = owner.id
             AND ra.chat_id = c.id
            LEFT JOIN analysis_window aw ON aw.chat_id = c.id
            GROUP BY c.id, ra.labels, ra.note
            ORDER BY max(aw.window_end) DESC NULLS LAST, c.updated_at DESC
            LIMIT $1
            """,
            limit,
        )
    items = [dict(row) for row in rows]
    for item in items:
        item["relationship_labels"] = _normalize_string_list(item.get("relationship_labels"))
    return items


async def get_conversation_detail_data(app: FastAPI, window_id: str) -> dict[str, Any]:
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                aw.id,
                aw.chat_id,
                aw.tg_chat_id,
                aw.chat_type,
                aw.window_start,
                aw.window_end,
                aw.summary,
                aw.confidence::float AS confidence,
                aw.source_message_ids,
                aw.participant_tg_ids,
                aw.messages,
                aw.features,
                aw.analysis_payload,
                c.title AS chat_title,
                c.is_allowed
            FROM analysis_window aw
            LEFT JOIN chat c ON c.id = aw.chat_id
            WHERE aw.id = $1::uuid
            """,
            window_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="window_not_found")
    item = dict(row)
    messages = item.get("messages")
    if isinstance(messages, str):
        try:
            messages = json.loads(messages)
        except json.JSONDecodeError:
            messages = []
    item["messages"] = messages if isinstance(messages, list) else []

    features = item.get("features")
    if isinstance(features, str):
        try:
            features = json.loads(features)
        except json.JSONDecodeError:
            features = {}
    item["features"] = features if isinstance(features, dict) else {}

    analysis_payload = item.get("analysis_payload") or {}
    if isinstance(analysis_payload, str):
        try:
            analysis_payload = json.loads(analysis_payload)
        except json.JSONDecodeError:
            analysis_payload = {}
    if not isinstance(analysis_payload, dict):
        analysis_payload = {}
    item["claims"] = analysis_payload.get("claims", [])
    item["tasks"] = analysis_payload.get("tasks", [])
    item["analytics_signals"] = analysis_payload.get("analytics_signals", [])
    return item


async def get_person_detail_data(app: FastAPI, person_id: str) -> dict[str, Any]:
    data = await get_person_context_data(app, person_id)
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        task_rows = await conn.fetch(
            """
            SELECT
                id,
                title,
                description,
                status,
                priority,
                confidence::float AS confidence,
                due_at
            FROM task
            WHERE owner_person_id = $1::uuid OR counterpart_person_id = $1::uuid
            ORDER BY created_at DESC
            LIMIT 10
            """,
            person_id,
        )
    data["tasks"] = [dict(row) for row in task_rows]
    return data


async def get_chat_detail_data(app: FastAPI, chat_id: str) -> dict[str, Any]:
    pool: asyncpg.Pool = app.state.db_pool
    owner_profile_id = await get_current_owner_profile_id(app)
    async with pool.acquire() as conn:
        chat = await conn.fetchrow(
            """
            SELECT
                c.id,
                c.tg_chat_id,
                c.kind,
                c.title,
                c.is_allowed,
                c.member_count,
                c.metadata,
                count(aw.id)::int AS window_count,
                max(aw.window_end) AS last_window_end
            FROM chat c
            LEFT JOIN analysis_window aw ON aw.chat_id = c.id
            WHERE c.id = $1::uuid
            GROUP BY c.id
            """,
            chat_id,
        )
        if chat is None:
            raise HTTPException(status_code=404, detail="chat_not_found")
        relationship_annotation = await conn.fetchrow(
            """
            SELECT
                labels,
                note,
                updated_at
            FROM relationship_annotation
            WHERE owner_profile_id = $1::uuid
              AND chat_id = $2::uuid
            LIMIT 1
            """,
            owner_profile_id,
            chat_id,
        )
        windows = await conn.fetch(
            """
            SELECT id, window_start, window_end, summary, confidence::float AS confidence
            FROM analysis_window
            WHERE chat_id = $1::uuid
            ORDER BY window_end DESC
            LIMIT 12
            """,
            chat_id,
        )
        tasks = await conn.fetch(
            """
            SELECT id, title, status, priority, confidence::float AS confidence, due_at
            FROM task
            WHERE chat_id = $1::uuid
            ORDER BY created_at DESC
            LIMIT 12
            """,
            chat_id,
        )
    relationship_payload = dict(relationship_annotation) if relationship_annotation is not None else {}
    relationship_payload["labels"] = _normalize_string_list(relationship_payload.get("labels"))
    relationship_payload["labels_preview"], relationship_payload["labels_hidden_count"] = _list_preview(
        relationship_payload["labels"],
        limit=8,
    )
    relationship_payload["note"] = _normalize_optional_text(cast("str | None", relationship_payload.get("note")))
    return {
        "chat": dict(chat),
        "windows": [dict(row) for row in windows],
        "tasks": [dict(row) for row in tasks],
        "relationship_annotation": relationship_payload,
    }


async def get_owner_profile_data(app: FastAPI) -> dict[str, Any]:
    owner_profile = await get_owner_profile_record(app)
    owner_person_id = (
        str(owner_profile["backing_person_id"])
        if owner_profile is not None and owner_profile.get("backing_person_id") is not None
        else await get_owner_person_id(app)
    )
    detail = await get_person_detail_data(app, owner_person_id)
    if owner_profile is None:
        owner_profile = {
            "id": None,
            "backing_person_id": detail["person"]["id"],
            "tg_user_id": detail["person"].get("tg_user_id"),
            "username": detail["person"].get("username"),
            "display_name": detail["person"].get("display_name"),
            "preferred_language": "ru",
            "context_tags": [],
            "context_tags_preview": [],
            "context_tags_hidden_count": 0,
            "profile_notes": detail["person"].get("notes"),
            "last_interaction_at": detail["person"].get("last_interaction_at"),
        }
    detail["person"]["display_name"] = owner_profile.get("display_name") or detail["person"].get("display_name")
    detail["person"]["username"] = owner_profile.get("username") or detail["person"].get("username")
    detail["person"]["tg_user_id"] = owner_profile.get("tg_user_id") or detail["person"].get("tg_user_id")
    detail["person"]["last_interaction_at"] = owner_profile.get("last_interaction_at") or detail["person"].get(
        "last_interaction_at"
    )
    detail["owner_profile"] = owner_profile
    detail["owner_profile_mode"] = True
    return detail


async def update_task_status(app: FastAPI, task_id: str, *, status: str) -> None:
    if status not in {"open", "done", "dropped"}:
        raise HTTPException(status_code=400, detail="invalid_task_status")
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE task
            SET status = $2,
                resolved_at = CASE WHEN $2 = 'done' THEN now() ELSE NULL END,
                updated_at = now()
            WHERE id = $1::uuid
            """,
            task_id,
            status,
        )
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="task_not_found")


async def set_person_blocked(app: FastAPI, person_id: str, *, blocked: bool) -> None:
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE person
            SET blocked = $2,
                updated_at = now()
            WHERE id = $1::uuid
            """,
            person_id,
            blocked,
        )
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="person_not_found")


async def update_person_annotations(
    app: FastAPI,
    person_id: str,
    *,
    manual_tags: list[str],
    notes: str | None,
) -> None:
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE person
            SET manual_tags = $2::text[],
                notes = $3,
                updated_at = now()
            WHERE id = $1::uuid
            """,
            person_id,
            manual_tags,
            notes,
        )
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="person_not_found")


async def update_owner_profile(
    app: FastAPI,
    *,
    context_tags: list[str],
    profile_notes: str | None,
    preferred_language: str,
) -> None:
    pool: asyncpg.Pool = app.state.db_pool
    owner_profile = await get_owner_profile_record(app)
    owner_person_id = await get_owner_person_id(app)
    async with pool.acquire() as conn:
        owner_person = await conn.fetchrow(
            """
            SELECT tg_user_id, username, display_name, last_interaction_at, notes
            FROM person
            WHERE id = $1::uuid
            """,
            owner_person_id,
        )
        if owner_person is None:
            raise HTTPException(status_code=404, detail="owner_profile_not_found")
        if owner_profile is None:
            await conn.execute(
                """
                INSERT INTO owner_profile (
                    backing_person_id,
                    tg_user_id,
                    username,
                    display_name,
                    preferred_language,
                    context_tags,
                    profile_notes,
                    last_interaction_at
                )
                VALUES ($1::uuid, $2, $3, $4, $5, $6::text[], $7, $8)
                """,
                owner_person_id,
                owner_person["tg_user_id"],
                owner_person["username"],
                owner_person["display_name"],
                preferred_language,
                context_tags,
                profile_notes,
                owner_person["last_interaction_at"],
            )
            return
        result = await conn.execute(
            """
            UPDATE owner_profile
            SET preferred_language = $2,
                context_tags = $3::text[],
                profile_notes = $4,
                backing_person_id = COALESCE(backing_person_id, $5::uuid),
                tg_user_id = COALESCE(tg_user_id, $6),
                username = COALESCE(username, $7),
                display_name = COALESCE(display_name, $8),
                last_interaction_at = COALESCE($9, last_interaction_at),
                updated_at = now()
            WHERE id = $1::uuid
            """,
            owner_profile["id"],
            preferred_language,
            context_tags,
            profile_notes,
            owner_person_id,
            owner_person["tg_user_id"],
            owner_person["username"],
            owner_person["display_name"],
            owner_person["last_interaction_at"],
        )
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="owner_profile_not_found")


async def update_person_relationship_annotation(
    app: FastAPI,
    person_id: str,
    *,
    labels: list[str],
    note: str | None,
) -> None:
    pool: asyncpg.Pool = app.state.db_pool
    owner_profile_id = await get_current_owner_profile_id(app)
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            INSERT INTO relationship_annotation (
                owner_profile_id,
                person_id,
                labels,
                note
            )
            VALUES ($1::uuid, $2::uuid, $3::text[], $4)
            ON CONFLICT (owner_profile_id, person_id)
            DO UPDATE SET
                labels = EXCLUDED.labels,
                note = EXCLUDED.note,
                updated_at = now()
            """,
            owner_profile_id,
            person_id,
            labels,
            note,
        )
    if not result.startswith(("INSERT", "UPDATE")):
        raise HTTPException(status_code=500, detail="relationship_annotation_write_failed")


async def update_chat_relationship_annotation(
    app: FastAPI,
    chat_id: str,
    *,
    labels: list[str],
    note: str | None,
) -> None:
    pool: asyncpg.Pool = app.state.db_pool
    owner_profile_id = await get_current_owner_profile_id(app)
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            INSERT INTO relationship_annotation (
                owner_profile_id,
                chat_id,
                labels,
                note
            )
            VALUES ($1::uuid, $2::uuid, $3::text[], $4)
            ON CONFLICT (owner_profile_id, chat_id)
            DO UPDATE SET
                labels = EXCLUDED.labels,
                note = EXCLUDED.note,
                updated_at = now()
            """,
            owner_profile_id,
            chat_id,
            labels,
            note,
        )
    if not result.startswith(("INSERT", "UPDATE")):
        raise HTTPException(status_code=500, detail="relationship_annotation_write_failed")


async def set_chat_allowlist(app: FastAPI, chat_id: str, *, is_allowed: bool) -> None:
    pool: asyncpg.Pool = app.state.db_pool
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE chat
            SET is_allowed = $2,
                updated_at = now()
            WHERE id = $1::uuid
            """,
            chat_id,
            is_allowed,
        )
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="chat_not_found")


async def get_person_context_data(app: FastAPI, person_id: str) -> dict[str, Any]:
    pool: asyncpg.Pool = app.state.db_pool
    qdrant: AsyncQdrantClient = app.state.qdrant
    neo4j_driver = app.state.neo4j_driver
    owner_profile_id = await get_current_owner_profile_id(app)

    async with pool.acquire() as conn:
        person = await conn.fetchrow(
            """
            SELECT
                id,
                tg_user_id,
                username,
                display_name,
                topics,
                organizations,
            manual_tags,
            notes,
            last_interaction_at,
            blocked,
            is_owner
        FROM person
        WHERE id = $1::uuid
        """,
        person_id,
        )
        if person is None:
            raise HTTPException(status_code=404, detail="person_not_found")

        relationship_annotation = await conn.fetchrow(
            """
            SELECT
                labels,
                note,
                updated_at
            FROM relationship_annotation
            WHERE owner_profile_id = $1::uuid
              AND person_id = $2::uuid
            LIMIT 1
            """,
            owner_profile_id,
            person_id,
        )

        windows: list[asyncpg.Record] = []
        if person["tg_user_id"] is not None:
            windows = await conn.fetch(
                """
                SELECT aw.id, aw.summary, aw.window_end, aw.analysis_payload
                     , aw.source_message_ids
                FROM analysis_window aw
                WHERE EXISTS (
                    SELECT 1
                    FROM unnest(aw.participant_tg_ids) AS participant_tg_id
                    WHERE participant_tg_id = $1::bigint
                )
                ORDER BY aw.window_end DESC
                LIMIT 5
                """,
                person["tg_user_id"],
            )

    async def load_semantic_hits() -> list[dict[str, Any]]:
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
        return [point.payload or {} for point in hits]

    async def load_graph_summary() -> list[dict[str, Any]]:
        if neo4j_driver is None:
            return []

        async def read_graph_neighbors(tx: Any) -> list[dict[str, Any]]:
            result = await tx.run(
                """
                MATCH (p:Person {id: $person_id})-[r:COMMUNICATED_WITH]-(other:Person)
                RETURN other.id AS person_id, coalesce(r.weight, 0) AS weight, r.last_window_id AS last_window_id
                ORDER BY weight DESC
                LIMIT 5
                """,
                person_id=person_id,
            )
            raw_records = cast("list[dict[str, Any]]", await result.data())
            return raw_records

        async with neo4j_driver.session(database=settings.neo4j_database) as session:
            records = await session.execute_read(read_graph_neighbors)
            return [dict(record) for record in records]

    semantic_result, graph_result = await asyncio.gather(
        _await_with_timeout(
            load_semantic_hits(),
            timeout_s=PERSON_DETAIL_QDRANT_TIMEOUT_S,
            fallback=[],
            status_name="semantic_memory",
        ),
        _await_with_timeout(
            load_graph_summary(),
            timeout_s=PERSON_DETAIL_NEO4J_TIMEOUT_S,
            fallback=[],
            status_name="graph_neighbors",
        ),
    )
    semantic_hits, semantic_status = semantic_result
    graph_summary, graph_status = graph_result

    person_payload = dict(person)
    person_payload["topics"] = _normalize_string_list(person_payload.get("topics"))
    person_payload["organizations"] = _normalize_string_list(person_payload.get("organizations"))
    person_payload["manual_tags"] = _normalize_string_list(person_payload.get("manual_tags"))
    person_payload["topics_preview"], person_payload["topics_hidden_count"] = _list_preview(
        person_payload["topics"],
        limit=12,
    )
    person_payload["organizations_preview"], person_payload["organizations_hidden_count"] = _list_preview(
        person_payload["organizations"],
        limit=6,
    )
    person_payload["manual_tags_preview"], person_payload["manual_tags_hidden_count"] = _list_preview(
        person_payload["manual_tags"],
        limit=8,
    )
    relationship_payload = dict(relationship_annotation) if relationship_annotation is not None else {}
    relationship_payload["labels"] = _normalize_string_list(relationship_payload.get("labels"))
    relationship_payload["labels_preview"], relationship_payload["labels_hidden_count"] = _list_preview(
        relationship_payload["labels"],
        limit=8,
    )
    relationship_payload["note"] = _normalize_optional_text(cast("str | None", relationship_payload.get("note")))

    return {
        "person": person_payload,
        "relationship_annotation": relationship_payload,
        "recent_windows": [dict(row) for row in windows],
        "semantic_memory": semantic_hits,
        "semantic_memory_preview": _semantic_memory_preview_items(semantic_hits),
        "graph_neighbors": graph_summary,
        "semantic_memory_status": semantic_status,
        "graph_neighbors_status": graph_status,
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


@router.get("/persons/{person_id}/brief")
@router.get("/v1/persons/{person_id}/brief", include_in_schema=False)
async def person_brief(request: Request, person_id: str) -> dict[str, Any]:
    return await synthesize_person_brief(request.app, person_id)


@router.api_route("/persons/{person_id}/erase", methods=["POST", "DELETE"])
@router.api_route("/v1/persons/{person_id}/erase", methods=["POST", "DELETE"], include_in_schema=False)
async def erase_person_api(
    request: Request,
    person_id: str,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    await _validate_person_erase_target(request.app, person_id)
    job_id = str(uuid.uuid4())
    request.app.state.jobs[job_id] = {"job_id": job_id, "person_id": person_id, "status": "queued"}
    background_tasks.add_task(_run_person_erase_job, request.app, job_id, person_id)
    return JSONResponse(
        status_code=202,
        headers={"Location": f"/jobs/{job_id}"},
        content={"job_id": job_id, "status": "queued"},
    )


@router.get("/jobs/{job_id}")
@router.get("/v1/jobs/{job_id}", include_in_schema=False)
async def job_status(request: Request, job_id: str) -> dict[str, Any]:
    jobs: dict[str, dict[str, Any]] = request.app.state.jobs
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")
    return job


@router.post("/reprocess/window")
async def reprocess_window(request: Request, window_id: str) -> dict[str, str]:
    redis: RedisClient = request.app.state.redis
    command = ReprocessWindowCommand(window_id=window_id)
    await redis.xadd(STREAM_AI_REPROCESS_WINDOW, {"data": command.model_dump_json()})
    return {"status": "queued", "window_id": window_id}


@router.get("/analytics", response_class=HTMLResponse, include_in_schema=False)
async def analytics_ui_alias() -> RedirectResponse:
    response = RedirectResponse(url="/admin", status_code=307)
    _apply_admin_no_cache_headers(response)
    return response


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def admin_root_alias() -> RedirectResponse:
    response = RedirectResponse(url="/admin", status_code=307)
    _apply_admin_no_cache_headers(response)
    return response


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_overview(request: Request) -> HTMLResponse:
    overview, conversations, tasks, people, chats, owner_profile = await asyncio.gather(
        get_analytics_overview_data(request.app),
        get_conversation_data(request.app, limit=6),
        get_open_tasks_data(request.app, limit=6),
        get_people_data(request.app, limit=6),
        get_chat_data(request.app, limit=6),
        get_owner_profile_data(request.app),
    )
    return _admin_template_response(
        request,
        name="admin_overview.html",
        context=_template_context(
            request,
            page_title="Пульт",
            current_page="overview",
            overview=overview,
            conversations=conversations,
            tasks=tasks,
            people=people,
            chats=chats,
            owner_profile=owner_profile,
        ),
    )


@router.get("/admin/me", response_class=HTMLResponse, include_in_schema=False)
async def admin_me(request: Request) -> HTMLResponse:
    detail = await get_owner_profile_data(request.app)
    return _admin_template_response(
        request,
        name="admin_person_detail.html",
        context=_template_context(
            request,
            page_title="Мой профиль",
            current_page="me",
            detail=detail,
        ),
    )


@router.post("/admin/me", include_in_schema=False)
async def admin_me_update(
    request: Request,
    form_data: Annotated[OwnerProfileForm, Form()],
) -> RedirectResponse:
    await update_owner_profile(
        request.app,
        context_tags=_parse_manual_tags(form_data.context_tags),
        profile_notes=_normalize_optional_text(form_data.profile_notes),
        preferred_language=_normalize_preferred_language(form_data.preferred_language),
    )
    return _redirect_with_flash("/admin/me", "owner_profile_saved")


@router.get("/admin/conversations", response_class=HTMLResponse, include_in_schema=False)
async def admin_conversations(request: Request, limit: int = 25) -> HTMLResponse:
    return _admin_template_response(
        request,
        name="admin_conversations.html",
        context=_template_context(
            request,
            page_title="Диалоги",
            current_page="conversations",
            conversations=await get_conversation_data(request.app, limit=limit),
            limit=limit,
        ),
    )


@router.get("/admin/conversations/{window_id}", response_class=HTMLResponse, include_in_schema=False)
async def admin_conversation_detail(request: Request, window_id: str) -> HTMLResponse:
    detail = await get_conversation_detail_data(request.app, window_id)
    return _admin_template_response(
        request,
        name="admin_conversation_detail.html",
        context=_template_context(
            request,
            page_title="Карточка окна",
            current_page="conversations",
            detail=detail,
        ),
    )


@router.post("/admin/conversations/{window_id}/reprocess", include_in_schema=False)
async def admin_reprocess_window(request: Request, window_id: str) -> RedirectResponse:
    redis: RedisClient = request.app.state.redis
    command = ReprocessWindowCommand(window_id=window_id)
    await redis.xadd(STREAM_AI_REPROCESS_WINDOW, {"data": command.model_dump_json()})
    return _redirect_with_flash(f"/admin/conversations/{window_id}", "window_requeued")


@router.get("/admin/tasks", response_class=HTMLResponse, include_in_schema=False)
async def admin_tasks(request: Request, limit: int = 50) -> HTMLResponse:
    return _admin_template_response(
        request,
        name="admin_tasks.html",
        context=_template_context(
            request,
            page_title="Задачи",
            current_page="tasks",
            tasks=await get_open_tasks_data(request.app, limit=limit),
            limit=limit,
        ),
    )


@router.post("/admin/tasks/{task_id}/status", include_in_schema=False)
async def admin_task_status(
    request: Request,
    task_id: str,
    status: Annotated[str, Form()],
    redirect_to: Annotated[str, Form()] = "/admin/tasks",
) -> RedirectResponse:
    await update_task_status(request.app, task_id, status=status)
    return _redirect_with_flash(redirect_to, f"task_status_{status}")


@router.get("/admin/people", response_class=HTMLResponse, include_in_schema=False)
async def admin_people(
    request: Request,
    limit: int = 50,
    manual_tag: str | None = None,
    relationship_label: str | None = None,
) -> HTMLResponse:
    return _admin_template_response(
        request,
        name="admin_people.html",
        context=_template_context(
            request,
            page_title="Люди",
            current_page="people",
            people=await get_people_data(
                request.app,
                limit=limit,
                manual_tag=manual_tag,
                relationship_label=relationship_label,
            ),
            limit=limit,
            active_manual_tag=_normalize_optional_text(manual_tag),
            active_relationship_label=_normalize_optional_text(relationship_label),
        ),
    )


@router.get("/admin/people/{person_id}", response_class=HTMLResponse, include_in_schema=False)
async def admin_person_detail(request: Request, person_id: str) -> Response:
    detail = await get_person_detail_data(request.app, person_id)
    if detail["person"].get("is_owner"):
        response = RedirectResponse(url="/admin/me", status_code=307)
        _apply_admin_no_cache_headers(response)
        return response
    return _admin_template_response(
        request,
        name="admin_person_detail.html",
        context=_template_context(
            request,
            page_title="Карточка профиля",
            current_page="people",
            detail=detail,
        ),
    )


@router.post("/admin/people/{person_id}/block", include_in_schema=False)
async def admin_person_block(
    request: Request,
    person_id: str,
    redirect_to: Annotated[str, Form()] = "/admin/people",
) -> RedirectResponse:
    owner_person_id = await get_owner_person_id(request.app)
    if person_id == owner_person_id:
        return _redirect_with_flash("/admin/me", "owner_profile_readonly")
    detail = await get_person_detail_data(request.app, person_id)
    current = bool(detail["person"]["blocked"])
    blocked = not current
    await set_person_blocked(request.app, person_id, blocked=blocked)
    flash_key = "person_blocked" if blocked else "person_unblocked"
    return _redirect_with_flash(redirect_to, flash_key)


@router.post("/admin/people/{person_id}/annotations", include_in_schema=False)
async def admin_person_annotations(
    request: Request,
    person_id: str,
    form_data: Annotated[PersonAnnotationsForm, Form()],
) -> RedirectResponse:
    owner_person_id = await get_owner_person_id(request.app)
    if person_id == owner_person_id:
        return _redirect_with_flash("/admin/me", "owner_profile_readonly")
    await update_person_annotations(
        request.app,
        person_id,
        manual_tags=_parse_manual_tags(form_data.manual_tags),
        notes=_normalize_optional_text(form_data.notes),
    )
    return _redirect_with_flash(form_data.redirect_to, "person_annotations_saved")


@router.post("/admin/people/{person_id}/relationship", include_in_schema=False)
async def admin_person_relationship_annotation(
    request: Request,
    person_id: str,
    form_data: Annotated[RelationshipAnnotationForm, Form()],
) -> RedirectResponse:
    owner_person_id = await get_owner_person_id(request.app)
    if person_id == owner_person_id:
        return _redirect_with_flash("/admin/me", "owner_profile_readonly")
    await update_person_relationship_annotation(
        request.app,
        person_id,
        labels=_parse_manual_tags(form_data.relationship_labels),
        note=_normalize_optional_text(form_data.relationship_note),
    )
    return _redirect_with_flash(form_data.redirect_to, "relationship_annotation_saved")


@router.post("/admin/people/{person_id}/erase", include_in_schema=False)
async def admin_person_erase(
    request: Request,
    person_id: str,
    redirect_to: Annotated[str, Form()] = "/admin/people",
) -> RedirectResponse:
    summary = await erase_person_cascade(request.app, person_id, actor="ui:owner")
    flash_key = "person_erased_with_warnings" if summary["warnings"] else "person_erased"
    return _redirect_with_flash(redirect_to, flash_key)


@router.get("/admin/chats", response_class=HTMLResponse, include_in_schema=False)
async def admin_chats(
    request: Request,
    limit: int = 50,
    relationship_label: str | None = None,
) -> HTMLResponse:
    chats = await get_chat_data(request.app, limit=limit)
    active_relationship_label = _normalize_optional_text(relationship_label)
    if active_relationship_label is not None:
        chats = [
            chat
            for chat in chats
            if active_relationship_label in _normalize_string_list(chat.get("relationship_labels"))
        ]
    return _admin_template_response(
        request,
        name="admin_chats.html",
        context=_template_context(
            request,
            page_title="Чаты",
            current_page="chats",
            chats=chats,
            limit=limit,
            active_relationship_label=active_relationship_label,
        ),
    )


@router.get("/admin/chats/{chat_id}", response_class=HTMLResponse, include_in_schema=False)
async def admin_chat_detail(request: Request, chat_id: str) -> HTMLResponse:
    detail = await get_chat_detail_data(request.app, chat_id)
    return _admin_template_response(
        request,
        name="admin_chat_detail.html",
        context=_template_context(
            request,
            page_title="Карточка чата",
            current_page="chats",
            detail=detail,
        ),
    )


@router.post("/admin/chats/{chat_id}/allowlist", include_in_schema=False)
async def admin_chat_allowlist(
    request: Request,
    chat_id: str,
    redirect_to: Annotated[str, Form()] = "/admin/chats",
) -> RedirectResponse:
    detail = await get_chat_detail_data(request.app, chat_id)
    current = bool(detail["chat"]["is_allowed"])
    allowed = not current
    await set_chat_allowlist(request.app, chat_id, is_allowed=allowed)
    flash_key = "chat_allowed" if allowed else "chat_disallowed"
    return _redirect_with_flash(redirect_to, flash_key)


@router.post("/admin/chats/{chat_id}/relationship", include_in_schema=False)
async def admin_chat_relationship_annotation(
    request: Request,
    chat_id: str,
    form_data: Annotated[RelationshipAnnotationForm, Form()],
) -> RedirectResponse:
    await update_chat_relationship_annotation(
        request.app,
        chat_id,
        labels=_parse_manual_tags(form_data.relationship_labels),
        note=_normalize_optional_text(form_data.relationship_note),
    )
    return _redirect_with_flash(form_data.redirect_to, "relationship_annotation_saved")


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
