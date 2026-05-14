from __future__ import annotations

from typing import TYPE_CHECKING, Any

import mcp_rest_api.app as mcp_app
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    import pytest


def _build_app(monkeypatch: pytest.MonkeyPatch) -> Any:
    async def fake_overview(_app: Any, days: int = 14) -> dict[str, Any]:
        return {
            "window_count": 7,
            "avg_confidence": 0.84,
            "avg_message_count": 12.5,
            "open_tasks": 2,
            "people_count": 3,
            "chat_count": 4,
            "signals": [{"signal_kind": "responsiveness", "avg_score": 0.66, "samples": 5}],
        }

    async def fake_conversations(_app: Any, limit: int = 20) -> list[dict[str, Any]]:
        return [
            {
                "id": "window-1",
                "tg_chat_id": 12345,
                "window_start": "2026-05-14 08:00",
                "window_end": "2026-05-14 08:15",
                "summary": "Discussed rollout details.",
                "confidence": 0.92,
                "message_count": 8,
                "signals": [{"kind": "responsiveness", "score": 0.72, "summary": "Fast replies"}],
            }
        ]

    async def fake_tasks(_app: Any, limit: int = 50) -> list[dict[str, Any]]:
        return [
            {
                "id": "task-1",
                "title": "Ship admin UI",
                "description": "Finish operator screens",
                "due_at": "2026-05-15 10:00",
                "priority": 1,
                "confidence": 0.88,
                "status": "open",
                "counterpart_name": "Ilyas",
                "tg_chat_id": 12345,
            }
        ]

    async def fake_people(_app: Any, limit: int = 50) -> list[dict[str, Any]]:
        return [
            {
                "id": "person-1",
                "tg_user_id": 77,
                "username": "ilyasni",
                "display_name": "Ilyas",
                "organizations": ["PIL"],
                "topics": ["ops", "memory"],
                "communication_style": "Concise and direct",
                "trust_score": 0.93,
                "last_interaction_at": "2026-05-14 08:20",
                "blocked": False,
            }
        ]

    async def fake_chats(_app: Any, limit: int = 50) -> list[dict[str, Any]]:
        return [
            {
                "id": "chat-1",
                "tg_chat_id": 12345,
                "kind": "private",
                "title": "Ops chat",
                "is_allowed": True,
                "member_count": 2,
                "window_count": 5,
                "last_window_end": "2026-05-14 08:15",
            }
        ]

    monkeypatch.setattr(mcp_app, "get_analytics_overview_data", fake_overview)
    monkeypatch.setattr(mcp_app, "get_conversation_data", fake_conversations)
    monkeypatch.setattr(mcp_app, "get_open_tasks_data", fake_tasks)
    monkeypatch.setattr(mcp_app, "get_people_data", fake_people)
    monkeypatch.setattr(mcp_app, "get_chat_data", fake_chats)
    return mcp_app.create_app(use_lifespan=False)


def test_analytics_redirects_to_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/analytics", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/admin"


def test_admin_overview_renders_dashboard(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/admin")
    assert response.status_code == 200
    assert "Control Room" in response.text
    assert "Discussed rollout details." in response.text
    assert "Ship admin UI" in response.text


def test_admin_people_links_context(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/admin/people")
    assert response.status_code == 200
    assert "ilyasni" in response.text
    assert "/persons/person-1/context" in response.text
