# ruff: noqa: E402
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "libs" / "contracts" / "src"))
sys.path.insert(0, str(ROOT / "libs" / "observability" / "src"))
sys.path.insert(0, str(ROOT / "libs" / "storage-clients" / "src"))
sys.path.insert(0, str(ROOT / "services" / "telegram-ingestor" / "src"))

from telegram_ingestor.handlers import _normalize_chat_type, _normalize_edit_date


def test_normalize_chat_type_falls_back_to_private() -> None:
    assert _normalize_chat_type("group") == "group"
    assert _normalize_chat_type("unexpected") == "private"


def test_normalize_edit_date_accepts_epoch_seconds() -> None:
    ts = datetime(2026, 5, 14, 10, 30, tzinfo=UTC).timestamp()

    normalized = _normalize_edit_date(ts)

    assert normalized == datetime(2026, 5, 14, 10, 30, tzinfo=UTC)
