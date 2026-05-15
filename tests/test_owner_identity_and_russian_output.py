# ruff: noqa: E402,I001,RUF001
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "libs" / "contracts" / "src"))
sys.path.insert(0, str(ROOT / "services" / "ai-orchestrator" / "src"))
sys.path.insert(0, str(ROOT / "services" / "memory-projector" / "src"))

from ai_orchestrator.llm import (
    _heuristic_analysis,
    _needs_russian_translation,
    _system_prompt,
    _user_prompt,
)
from ai_orchestrator.preprocessing import compute_message_features
from memory_projector.consumer import _matches_owner_identity
from memory_projector.settings import settings as projector_settings
from pil_contracts.events import WindowMessagePayload


def test_system_and_user_prompts_require_russian_output() -> None:
    message = WindowMessagePayload(
        tg_message_id=1,
        tg_sender_id=139883458,
        tg_sender_name="Ilya",
        tg_sender_username="ilyasni",
        text="Please send the contract tomorrow.",
        occurred_at=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
    )
    features = compute_message_features([message], chat_type="private")

    system_prompt = _system_prompt()
    user_prompt = _user_prompt(
        source_window_id="window-1",
        messages=[message],
        features=features,
        canonical_context={},
    )

    assert "на русском языке" in system_prompt
    assert "на русском языке" in user_prompt
    assert "@ilyasni" in user_prompt


def test_heuristic_analysis_uses_russian_text() -> None:
    message = WindowMessagePayload(
        tg_message_id=1,
        tg_sender_id=100,
        tg_sender_name="Anna",
        text="Напиши мне на anna@example.com и проверь https://example.com",
        occurred_at=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
    )
    features = compute_message_features([message], chat_type="private")

    result = _heuristic_analysis(
        source_window_id="window-1",
        messages=[message],
        features=features,
    )

    assert result.caveats == ["Результат сформирован без ответа внешней LLM."]
    assert any("В переписке был передан адрес электронной почты" in claim.claim for claim in result.claims)
    assert any("Оценка построена" in signal.summary for signal in result.analytics_signals)


def test_english_result_is_marked_for_russian_translation() -> None:
    message = WindowMessagePayload(
        tg_message_id=1,
        tg_sender_id=100,
        tg_sender_name="Anna",
        text="Please review the contract tomorrow.",
        occurred_at=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
    )
    features = compute_message_features([message], chat_type="private")

    result = _heuristic_analysis(
        source_window_id="window-1",
        messages=[message],
        features=features,
    ).model_copy(
        update={
            "summary": "Please review the contract tomorrow.",
        }
    )

    assert _needs_russian_translation(result, target_language="ru") is True
    assert _needs_russian_translation(result, target_language="en") is False


def test_matches_owner_identity_by_id_and_username() -> None:
    original_ids = projector_settings.owner_tg_user_ids
    original_usernames = projector_settings.owner_usernames
    original_display_names = projector_settings.owner_display_names
    try:
        projector_settings.owner_tg_user_ids = "139883458"
        projector_settings.owner_usernames = "@ilyasni"
        projector_settings.owner_display_names = "Ilya"

        assert _matches_owner_identity(
            tg_user_id=139883458,
            username="other",
            display_name="Someone",
        )
        assert _matches_owner_identity(
            tg_user_id=1,
            username="ilyasni",
            display_name="Someone",
        )
        assert _matches_owner_identity(
            tg_user_id=1,
            username="other",
            display_name="Ilya",
        )
        assert not _matches_owner_identity(
            tg_user_id=1,
            username="other",
            display_name="Someone",
        )
    finally:
        projector_settings.owner_tg_user_ids = original_ids
        projector_settings.owner_usernames = original_usernames
        projector_settings.owner_display_names = original_display_names
