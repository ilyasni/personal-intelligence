from __future__ import annotations

from datetime import datetime


def needs_rollover(
    *,
    last_occurred_at: datetime,
    occurred_at: datetime,
    strategy: str,
    time_window_minutes: int,
) -> bool:
    if strategy not in {"by_time_window", "hybrid"}:
        return False

    gap_seconds = (occurred_at - last_occurred_at).total_seconds()
    return gap_seconds >= max(60, time_window_minutes * 60)
