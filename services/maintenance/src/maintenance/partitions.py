from dataclasses import dataclass
from datetime import datetime, timezone


PARTITIONED_TABLES: dict[str, str] = {
    "interaction": "created_at",
    "processed_event": "processed_at",
    "audit_log": "ts",
}


@dataclass(frozen=True)
class PartitionSpec:
    table: str
    column: str
    name: str
    start: datetime
    end: datetime


def monthly_partition_specs(
    *,
    now: datetime,
    months_ahead: int,
) -> list[PartitionSpec]:
    base = month_start(now)
    total = max(1, months_ahead)
    specs: list[PartitionSpec] = []
    for offset in range(total):
        start = add_months(base, offset)
        end = add_months(start, 1)
        suffix = start.strftime("%Y_%m")
        for table, column in PARTITIONED_TABLES.items():
            specs.append(
                PartitionSpec(
                    table=table,
                    column=column,
                    name=f"{table}_{suffix}",
                    start=start,
                    end=end,
                )
            )
    return specs


def month_start(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def add_months(dt: datetime, months: int) -> datetime:
    year = dt.year + (dt.month - 1 + months) // 12
    month = (dt.month - 1 + months) % 12 + 1
    return dt.replace(year=year, month=month, day=1)


def create_partition_sql(spec: PartitionSpec) -> str:
    start = spec.start.strftime("%Y-%m-%d")
    end = spec.end.strftime("%Y-%m-%d")
    return (
        f"CREATE TABLE IF NOT EXISTS {spec.name} PARTITION OF {spec.table} "
        f"FOR VALUES FROM ('{start}') TO ('{end}')"
    )

