from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from typing import Any

import asyncpg

from ai_orchestrator.consumer import (
    _flush_window,
    _handle_message,
    _load_canonical_context,
    _load_window_messages,
)
from ai_orchestrator.graph import build_analysis_graph
from ai_orchestrator.llm import AnalysisRouter
from ai_orchestrator.settings import settings
from pil_contracts import STREAM_TELEGRAM_MESSAGE, TelegramMessageEvent
from pil_observability import configure_logging, get_logger
from pil_storage import RedisClient

log = get_logger("ai-orchestrator.backfill")


@dataclass(slots=True)
class BackfillStats:
    scanned: int = 0
    skipped: int = 0
    handled: int = 0
    flushed: int = 0
    failed: int = 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay Redis telegram history through ai-orchestrator.")
    parser.add_argument(
        "--exclude-chat-id",
        action="append",
        default=[],
        type=int,
        help="Telegram chat id to skip. Can be passed multiple times.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=0,
        help="Limit the number of Redis stream entries to replay. 0 means all available entries.",
    )
    parser.add_argument(
        "--skip-obvious-test-data",
        action="store_true",
        help="Skip placeholder/demo events such as synthetic Message N streams.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only scan and report candidate events without replaying them.",
    )
    return parser.parse_args()


def _is_obvious_test_event(event: TelegramMessageEvent) -> bool:
    text = (event.text or "").strip()
    if event.tg_chat_id == 990001:
        return True
    if event.tg_sender_username in {"owner", "partner"}:
        return True
    return text.startswith("Message ") and "normal project sync" in text


async def _iter_events(
    redis: RedisClient,
    *,
    max_events: int,
) -> list[TelegramMessageEvent]:
    if max_events > 0:
        raw_entries = await redis.r.xrange(STREAM_TELEGRAM_MESSAGE, count=max_events)
    else:
        raw_entries = await redis.r.xrange(STREAM_TELEGRAM_MESSAGE)
    return [
        TelegramMessageEvent.model_validate_json(str(fields.get("data", "{}")))
        for _msg_id, fields in raw_entries
    ]


async def _flush_residual_windows(
    *,
    redis: RedisClient,
    db_pool: asyncpg.Pool,
    analysis_graph: Any,
    last_seen_by_chat: dict[int, TelegramMessageEvent],
) -> tuple[int, int]:
    flushed = 0
    failed = 0
    for tg_chat_id, last_event in last_seen_by_chat.items():
        if not await _load_window_messages(redis, tg_chat_id):
            continue
        try:
            await _flush_window(
                redis=redis,
                db_pool=db_pool,
                analysis_graph=analysis_graph,
                tg_chat_id=tg_chat_id,
                source_event_id=last_event.event_id,
                chat_type=last_event.chat_type,
                trace_id=last_event.trace_id,
            )
            flushed += 1
        except Exception as exc:
            failed += 1
            log.error("backfill_flush_failed", tg_chat_id=tg_chat_id, error=str(exc))
    return flushed, failed


async def _run_backfill(args: argparse.Namespace) -> BackfillStats:
    redis = RedisClient(url=settings.redis_url, password=settings.redis_password or None)
    pg_dsn = settings.postgres_dsn.replace("postgresql+asyncpg://", "postgresql://")
    db_pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=6)
    router = AnalysisRouter()
    stats = BackfillStats()
    excluded_chat_ids = set(args.exclude_chat_id)
    last_seen_by_chat: dict[int, TelegramMessageEvent] = {}

    try:
        events = await _iter_events(redis, max_events=args.max_events)
        analysis_graph = build_analysis_graph(
            router=router,
            context_loader=lambda tg_chat_id, messages: _load_canonical_context(db_pool, tg_chat_id, messages),
        )
        for event in events:
            stats.scanned += 1
            if event.tg_chat_id in excluded_chat_ids:
                stats.skipped += 1
                continue
            if args.skip_obvious_test_data and _is_obvious_test_event(event):
                stats.skipped += 1
                continue
            last_seen_by_chat[event.tg_chat_id] = event
            if args.dry_run:
                continue
            try:
                await _handle_message(event, redis, db_pool, analysis_graph)
                stats.handled += 1
            except Exception as exc:
                stats.failed += 1
                log.error("backfill_event_failed", tg_chat_id=event.tg_chat_id, event_id=event.event_id, error=str(exc))

        if not args.dry_run:
            stats.flushed, flush_failed = await _flush_residual_windows(
                redis=redis,
                db_pool=db_pool,
                analysis_graph=analysis_graph,
                last_seen_by_chat=last_seen_by_chat,
            )
            stats.failed += flush_failed
    finally:
        await router.close()
        await db_pool.close()
        await redis.aclose()
    return stats


async def main() -> None:
    args = _parse_args()
    configure_logging(level=settings.log_level, service="ai-orchestrator-backfill")
    stats = await _run_backfill(args)
    log.info(
        "backfill_completed",
        scanned=stats.scanned,
        skipped=stats.skipped,
        handled=stats.handled,
        flushed=stats.flushed,
        failed=stats.failed,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    asyncio.run(main())
