import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "maintenance" / "src"))

from maintenance.partitions import create_partition_sql, monthly_partition_specs


def test_monthly_partition_specs_include_all_partitioned_tables() -> None:
    specs = monthly_partition_specs(
        now=datetime(2026, 5, 12, tzinfo=UTC),
        months_ahead=2,
    )

    names = {spec.name for spec in specs}
    assert "interaction_2026_05" in names
    assert "processed_event_2026_06" in names
    assert "audit_log_2026_06" in names
    assert len(specs) == 6


def test_create_partition_sql_uses_expected_bounds() -> None:
    spec = monthly_partition_specs(
        now=datetime(2026, 5, 12, tzinfo=UTC),
        months_ahead=1,
    )[0]

    sql = create_partition_sql(spec)

    assert "CREATE TABLE IF NOT EXISTS interaction_2026_05 PARTITION OF interaction" in sql
    assert "FOR VALUES FROM ('2026-05-01') TO ('2026-06-01')" in sql
