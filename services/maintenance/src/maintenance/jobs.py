from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
from pil_observability import get_logger

from maintenance.partitions import PARTITIONED_TABLES, create_partition_sql, monthly_partition_specs

log = get_logger("maintenance.jobs")

async def ensure_runtime_defaults(
    conn: asyncpg.Connection,
    *,
    default_months_ahead: int,
    default_processed_event_retention_days: int,
) -> None:
    default_setting_keys: dict[str, Any] = {
        "maintenance.partition_months_ahead": default_months_ahead,
        "maintenance.processed_event_retention_days": default_processed_event_retention_days,
    }
    for key, value in default_setting_keys.items():
        await conn.execute(
            """
            INSERT INTO setting (key, value)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (key) DO NOTHING
            """,
            key,
            _json_scalar(value),
        )


async def run_maintenance(
    pool: asyncpg.Pool,
    *,
    default_months_ahead: int,
    default_processed_event_retention_days: int,
    advisory_lock_key: int,
) -> None:
    async with pool.acquire() as conn:
        locked = await conn.fetchval("SELECT pg_try_advisory_lock($1)", advisory_lock_key)
        if not locked:
            log.info("maintenance_skipped_locked")
            return

        try:
            await ensure_runtime_defaults(
                conn,
                default_months_ahead=default_months_ahead,
                default_processed_event_retention_days=default_processed_event_retention_days,
            )

            months_ahead = await get_int_setting(
                conn,
                "maintenance.partition_months_ahead",
                default_months_ahead,
            )
            processed_event_retention_days = await get_int_setting(
                conn,
                "maintenance.processed_event_retention_days",
                default_processed_event_retention_days,
            )

            created = await ensure_future_partitions(conn, months_ahead=months_ahead)
            dropped = await drop_expired_processed_event_partitions(
                conn,
                retention_days=processed_event_retention_days,
            )
            deleted = await trim_processed_event_boundary_rows(
                conn,
                retention_days=processed_event_retention_days,
            )

            log.info(
                "maintenance_completed",
                created_partitions=created,
                dropped_partitions=dropped,
                deleted_rows=deleted,
                months_ahead=months_ahead,
                processed_event_retention_days=processed_event_retention_days,
            )
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", advisory_lock_key)


async def ensure_future_partitions(
    conn: asyncpg.Connection,
    *,
    months_ahead: int,
    now: datetime | None = None,
) -> int:
    current = now or datetime.now(UTC)
    created = 0
    for spec in monthly_partition_specs(now=current, months_ahead=months_ahead):
        sql = create_partition_sql(spec)
        existed = await _relation_exists(conn, spec.name)
        await conn.execute(sql)
        if not existed:
            created += 1
    return created


async def drop_expired_processed_event_partitions(
    conn: asyncpg.Connection,
    *,
    retention_days: int,
    now: datetime | None = None,
) -> int:
    current = now or datetime.now(UTC)
    cutoff = current - timedelta(days=max(1, retention_days))
    cutoff_month = cutoff.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    partitions = await conn.fetch(
        """
        SELECT c.relname AS partition_name
        FROM pg_inherits
        JOIN pg_class p ON pg_inherits.inhparent = p.oid
        JOIN pg_class c ON pg_inherits.inhrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE p.relname = 'processed_event'
          AND n.nspname = current_schema()
        ORDER BY c.relname
        """
    )

    dropped = 0
    for row in partitions:
        name = row["partition_name"]
        suffix = name.removeprefix("processed_event_")
        try:
            start = datetime.strptime(suffix, "%Y_%m").replace(tzinfo=UTC)
        except ValueError:
            continue
        end = _add_month(start, 1)
        if end <= cutoff_month:
            await conn.execute(f"DROP TABLE IF EXISTS {name}")
            dropped += 1
    return dropped


async def trim_processed_event_boundary_rows(
    conn: asyncpg.Connection,
    *,
    retention_days: int,
    now: datetime | None = None,
) -> int:
    current = now or datetime.now(UTC)
    cutoff = current - timedelta(days=max(1, retention_days))
    result = await conn.execute(
        "DELETE FROM processed_event WHERE processed_at < $1",
        cutoff,
    )
    return _parse_deleted_count(result)


async def get_int_setting(
    conn: asyncpg.Connection,
    key: str,
    default: int,
) -> int:
    value = await conn.fetchval("SELECT value FROM setting WHERE key = $1", key)
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


async def _relation_exists(conn: asyncpg.Connection, relation_name: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", relation_name))


def _parse_deleted_count(status: str) -> int:
    try:
        return int(status.split()[-1])
    except (IndexError, ValueError):
        return 0


def _add_month(dt: datetime, months: int) -> datetime:
    year = dt.year + (dt.month - 1 + months) // 12
    month = (dt.month - 1 + months) % 12 + 1
    return dt.replace(year=year, month=month, day=1)


def _json_scalar(value: Any) -> str:
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)
