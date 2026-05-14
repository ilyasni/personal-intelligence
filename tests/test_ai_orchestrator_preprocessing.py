# ruff: noqa: E402
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "libs" / "contracts" / "src"))
sys.path.insert(0, str(ROOT / "services" / "ai-orchestrator" / "src"))

from ai_orchestrator.preprocessing import (
    compute_message_features,
    needs_rollover,
    topic_drift_score,
)

from pil_contracts.events import WindowMessagePayload


def test_compute_message_features_extracts_deterministic_signals() -> None:
    start = datetime(2026, 5, 13, 10, 0, tzinfo=UTC)
    messages = [
        WindowMessagePayload(
            tg_message_id=1,
            tg_sender_id=100,
            tg_sender_name="Ilya",
            text="Please email me at ilya@example.com and check https://example.com",
            occurred_at=start,
        ),
        WindowMessagePayload(
            tg_message_id=2,
            tg_sender_id=200,
            tg_sender_name="Anna",
            text="Thanks, call me at +7 (999) 111-22-33",
            reply_to_message_id=1,
            media_type="document",
            occurred_at=start + timedelta(minutes=5),
        ),
        WindowMessagePayload(
            tg_message_id=3,
            tg_sender_id=100,
            tg_sender_name="Ilya",
            text="Urgent: send the draft to @annadev",
            is_forwarded=True,
            occurred_at=start + timedelta(minutes=20),
        ),
    ]

    features = compute_message_features(messages, chat_type="private")

    assert features.message_count == 3
    assert features.participant_count == 2
    assert features.emails == ["ilya@example.com"]
    assert features.links == ["https://example.com"]
    assert features.phones == ["79991112233"]
    assert features.reply_count == 1
    assert features.attachment_count == 1
    assert features.forwarded_count == 1
    assert features.sentiment_hint in {"mixed", "negative"}
    assert features.median_response_latency_sec == 600.0


def test_rollover_and_topic_drift_follow_window_rules() -> None:
    start = datetime(2026, 5, 13, 10, 0, tzinfo=UTC)
    assert needs_rollover(
        last_occurred_at=start,
        occurred_at=start + timedelta(minutes=61),
        strategy="hybrid",
        time_window_minutes=60,
    )

    messages = [
        WindowMessagePayload(
            tg_message_id=1,
            tg_sender_id=1,
            text="contract budget invoice",
            occurred_at=start,
        ),
        WindowMessagePayload(
            tg_message_id=2,
            tg_sender_id=2,
            text="meeting roadmap hiring",
            occurred_at=start + timedelta(minutes=1),
        ),
    ]
    assert topic_drift_score(messages) == 1.0


def test_compute_message_features_normalizes_unknown_window_metadata() -> None:
    start = datetime(2026, 5, 13, 12, 0, tzinfo=UTC)
    messages = [
        WindowMessagePayload(
            tg_message_id=1,
            tg_sender_id=1,
            text="hello world",
            occurred_at=start,
        )
    ]

    features = compute_message_features(
        messages,
        chat_type="unexpected",
        window_kind="unknown",
    )

    assert features.chat_type == "private"
    assert features.window_kind == "rolling"
