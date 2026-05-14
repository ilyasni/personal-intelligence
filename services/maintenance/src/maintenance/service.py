import asyncio
import signal

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pil_observability import get_logger

from maintenance.jobs import run_maintenance
from maintenance.settings import settings

log = get_logger("maintenance.service")


async def run() -> None:
    pg_dsn = settings.postgres_dsn.replace("postgresql+asyncpg://", "postgresql://")
    pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=4)
    log.info("postgres_connected")

    scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
    stop_event = asyncio.Event()

    try:
        if settings.startup_run:
            await _run_job(pool)

        scheduler.add_job(
            _run_job,
            trigger="interval",
            hours=settings.maintenance_interval_hours,
            kwargs={"pool": pool},
            id="daily-maintenance",
            coalesce=True,
            max_instances=settings.scheduler_max_instances,
            misfire_grace_time=settings.scheduler_misfire_grace_seconds,
            jitter=settings.scheduler_jitter_seconds,
            replace_existing=True,
        )
        scheduler.start()
        log.info(
            "scheduler_started",
            interval_hours=settings.maintenance_interval_hours,
            timezone=settings.scheduler_timezone,
        )

        _install_signal_handlers(stop_event)
        await stop_event.wait()
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await pool.close()


async def _run_job(pool: asyncpg.Pool) -> None:
    await run_maintenance(
        pool,
        default_months_ahead=settings.partition_months_ahead,
        default_processed_event_retention_days=settings.processed_event_retention_days,
        advisory_lock_key=settings.advisory_lock_key,
    )


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for signame in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signame, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass
