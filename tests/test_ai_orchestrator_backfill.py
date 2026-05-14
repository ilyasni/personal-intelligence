from __future__ import annotations

from datetime import UTC, datetime

from ai_orchestrator.backfill import _is_obvious_test_event
from ai_orchestrator.consumer import _coerce_json_value, _coerce_window_messages

from pil_contracts import TelegramMessageEvent


def test_coerce_window_messages_accepts_json_string() -> None:
    raw = """
    [
      {
        "tg_message_id": 1,
        "tg_sender_id": 10,
        "tg_sender_name": "Ilya",
        "tg_sender_username": "ilyasni",
        "text": "Привет",
        "reply_to_message_id": null,
        "media_type": null,
        "is_forwarded": false,
        "occurred_at": "2026-05-14T18:00:00Z"
      }
    ]
    """
    messages = _coerce_window_messages(raw)
    assert len(messages) == 1
    assert messages[0].tg_message_id == 1
    assert messages[0].text == "Привет"


def test_coerce_window_messages_rejects_invalid_payload() -> None:
    assert _coerce_window_messages("{bad json") == []
    assert _coerce_window_messages({"not": "a list"}) == []


def test_coerce_json_value_unwraps_nested_json_string() -> None:
    nested = '"{\\"topics\\": [\\"ops\\", \\"memory\\"]}"'
    assert _coerce_json_value(nested) == {"topics": ["ops", "memory"]}


def test_is_obvious_test_event_detects_demo_chat() -> None:
    event = TelegramMessageEvent(
        tg_chat_id=990001,
        tg_message_id=7000,
        tg_sender_id=1001,
        tg_sender_username="owner",
        tg_sender_name="Owner",
        chat_title=None,
        chat_type="private",
        text="Message 0: normal project sync about contracts and timelines",
        occurred_at=datetime.now(tz=UTC),
    )
    assert _is_obvious_test_event(event) is True


def test_is_obvious_test_event_keeps_real_message() -> None:
    event = TelegramMessageEvent(
        tg_chat_id=105957884,
        tg_message_id=1,
        tg_sender_id=123,
        tg_sender_username="shanskiy",
        tg_sender_name="Andrey Shanskiy",
        chat_title="Andrey Shanskiy",
        chat_type="private",
        text="Привет! Буду из дома сегодня.",
        occurred_at=datetime.now(tz=UTC),
    )
    assert _is_obvious_test_event(event) is False
