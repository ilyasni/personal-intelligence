import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "libs" / "llm-client" / "src"))

from pil_llm import parse_summary_payload  # noqa: E402


def test_parse_summary_payload_from_json_block() -> None:
    payload = parse_summary_payload(
        """
        {"topics":["release","billing"],"sentiment":"mixed","summary":"Release discussion is blocked by one billing issue.","tasks":["check invoice"]}
        """,
        max_summary_chars=120,
    )

    assert payload.topics == ["release", "billing"]
    assert payload.sentiment == "mixed"
    assert payload.summary == "Release discussion is blocked by one billing issue."
    assert payload.tasks == ["check invoice"]


def test_parse_summary_payload_falls_back_to_plain_text() -> None:
    payload = parse_summary_payload(
        "Plain summary without JSON wrapper",
        max_summary_chars=20,
    )

    assert payload.topics == []
    assert payload.sentiment == "neutral"
    assert payload.summary == "Plain summary wit..."


def test_parse_summary_payload_recovers_from_fenced_partial_json() -> None:
    payload = parse_summary_payload(
        """
        ```json
        {
          "summary": "Мария — близкий контакт владельца и общение касается дома и повседневных дел.",
          "topics": ["семья", "дом"],
          "tasks": ["Купить продукты", "Позвонить вечером"]
        ```
        """,
        max_summary_chars=160,
    )

    assert payload.summary == "Мария — близкий контакт владельца и общение касается дома и повседневных дел."
    assert payload.topics == ["семья", "дом"]
    assert payload.tasks == ["Купить продукты", "Позвонить вечером"]


def test_parse_summary_payload_recovers_from_truncated_summary_field() -> None:
    payload = parse_summary_payload(
        """
        {
          "summary": "Мария — близкий контакт владельца. Обсуждали дом, самочувствие и рабочие задачи",
          "topics": ["семья", "самочувствие"]
        """,
        max_summary_chars=160,
    )

    assert payload.summary == "Мария — близкий контакт владельца. Обсуждали дом, самочувствие и рабочие задачи"
    assert payload.topics == ["семья", "самочувствие"]
