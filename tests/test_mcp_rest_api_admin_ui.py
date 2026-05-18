from __future__ import annotations

from typing import TYPE_CHECKING, Any

import mcp_rest_api.app as mcp_app
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    import pytest


def _build_app(monkeypatch: pytest.MonkeyPatch) -> Any:
    state: dict[str, Any] = {
        "task_updates": [],
        "allowlist_updates": [],
        "person_block_updates": [],
        "person_annotation_updates": [],
        "owner_profile_updates": [],
        "relationship_annotation_updates": [],
        "chat_relationship_annotation_updates": [],
        "person_erase_updates": [],
    }

    async def fake_overview(_app: Any, days: int = 14) -> dict[str, Any]:
        return {
            "window_count": 7,
            "avg_confidence": 0.84,
            "avg_message_count": 12.5,
            "open_tasks": 2,
            "people_count": 3,
            "owner_profile_count": 1,
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

    async def fake_people(
        _app: Any,
        limit: int = 50,
        *,
        manual_tag: str | None = None,
        relationship_label: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": "person-1",
                "tg_user_id": 77,
                "username": "ilyasni",
                "display_name": "Ilyas",
                "organizations": ["PIL"],
                "topics": ["ops", "memory"],
                "manual_tags": ["коллега", "pet-проект"],
                "communication_style": "Concise and direct",
                "trust_score": 0.93,
                "last_interaction_at": "2026-05-14 08:20",
                "blocked": False,
                "is_owner": False,
                "relationship_labels": ["коллега", "frontier"],
                "relationship_note": "Ключевой коллега по рабочему контуру.",
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
                "relationship_labels": ["работа", "pil"],
                "relationship_note": "Основной рабочий чат по админке и runtime.",
            }
        ]

    async def fake_conversation_detail(_app: Any, window_id: str) -> dict[str, Any]:
        return {
            "id": window_id,
            "tg_chat_id": 12345,
            "chat_title": "Ops chat",
            "chat_type": "private",
            "window_start": "2026-05-14 08:00",
            "window_end": "2026-05-14 08:15",
            "summary": "Discussed rollout details.",
            "confidence": 0.92,
            "source_message_ids": [101, 102],
            "participant_tg_ids": [77, 88],
            "is_allowed": True,
            "features": {"message_count": 8, "contains_questions": True},
            "messages": [
                {
                    "tg_message_id": 101,
                    "occurred_at": "2026-05-14 08:01",
                    "author_display_name": "Ilyas",
                    "author_tg_user_id": 77,
                    "text": "Need to ship admin UI.",
                }
            ],
            "claims": [
                {
                    "kind": "task",
                    "claim": "Need to ship admin UI",
                    "confidence": 0.88,
                    "evidence_message_ids": [101],
                }
            ],
            "tasks": [
                {
                    "title": "Ship admin UI",
                    "description": "Finish operator screens",
                    "status": "open",
                    "confidence": 0.88,
                }
            ],
            "analytics_signals": [
                {"kind": "responsiveness", "score": 0.72, "summary": "Fast replies"}
            ],
        }

    async def fake_person_detail(_app: Any, person_id: str) -> dict[str, Any]:
        return {
            "person": {
                "id": person_id,
                "username": "ilyasni",
                "display_name": "Ilyas",
                "last_interaction_at": "2026-05-14 08:20",
                "topics": ["ops", "memory"],
                "organizations": ["PIL"],
                "manual_tags": ["коллега", "pet-проект"],
                "notes": "Основной контакт по проекту.",
                "blocked": False,
                "is_owner": False,
            },
            "relationship_annotation": {
                "labels": ["коллега", "frontier"],
                "labels_preview": ["коллега", "frontier"],
                "labels_hidden_count": 0,
                "note": "Ключевой коллега по рабочему контуру.",
            },
            "recent_windows": [{"id": "window-1", "summary": "Discussed rollout details.", "window_end": "2026-05-14 08:15"}],
            "tasks": [{"title": "Ship admin UI", "description": "Finish operator screens", "status": "open", "due_at": "2026-05-15 10:00"}],
            "graph_neighbors": [{"person_id": "person-2", "weight": 0.8, "last_window_id": "window-1"}],
            "semantic_memory": [{"kind": "analysis_window", "summary": "Discussed rollout details."}],
            "graph_neighbors_status": "ok",
            "semantic_memory_status": "ok",
        }

    async def fake_owner_profile(_app: Any) -> dict[str, Any]:
        return {
            "person": {
                "id": "owner-1",
                "username": "ilyasni",
                "display_name": "Ilya",
                "last_interaction_at": "2026-05-14 08:20",
                "topics": ["работа", "pil", "память"],
                "topics_preview": ["работа", "pil", "память"],
                "topics_hidden_count": 0,
                "organizations": ["PIL"],
                "organizations_preview": ["PIL"],
                "organizations_hidden_count": 0,
                "manual_tags": [],
                "manual_tags_preview": [],
                "manual_tags_hidden_count": 0,
                "notes": None,
                "blocked": False,
                "is_owner": True,
            },
            "relationship_annotation": {
                "labels": [],
                "labels_preview": [],
                "labels_hidden_count": 0,
                "note": None,
            },
            "owner_profile": {
                "id": "owner-profile-1",
                "backing_person_id": "owner-1",
                "tg_user_id": 139883458,
                "username": "ilyasni",
                "display_name": "Ilya",
                "preferred_language": "ru",
                "context_tags": ["работа", "pil"],
                "context_tags_preview": ["работа", "pil"],
                "context_tags_hidden_count": 0,
                "profile_notes": "Русский — основной язык аналитики.",
                "last_interaction_at": "2026-05-14 08:20",
            },
            "recent_windows": [{"id": "window-1", "summary": "Discussed rollout details.", "window_end": "2026-05-14 08:15"}],
            "tasks": [{"title": "Ship admin UI", "description": "Finish operator screens", "status": "open", "due_at": "2026-05-15 10:00"}],
            "graph_neighbors": [],
            "semantic_memory": [],
            "graph_neighbors_status": "ok",
            "semantic_memory_status": "ok",
            "owner_profile_mode": True,
        }

    async def fake_chat_detail(_app: Any, chat_id: str) -> dict[str, Any]:
        return {
            "chat": {
                "id": chat_id,
                "tg_chat_id": 12345,
                "kind": "private",
                "title": "Ops chat",
                "is_allowed": True,
                "member_count": 2,
                "window_count": 5,
                "last_window_end": "2026-05-14 08:15",
                "metadata": {"source": "telegram"},
            },
            "relationship_annotation": {
                "labels": ["работа", "pil"],
                "labels_preview": ["работа", "pil"],
                "labels_hidden_count": 0,
                "note": "Основной рабочий чат по админке и runtime.",
            },
            "windows": [{"id": "window-1", "window_end": "2026-05-14 08:15", "summary": "Discussed rollout details.", "confidence": 0.92}],
            "tasks": [{"title": "Ship admin UI", "status": "open", "priority": 1, "confidence": 0.88, "due_at": "2026-05-15 10:00"}],
        }

    async def fake_update_task_status(_app: Any, task_id: str, *, status: str) -> None:
        state["task_updates"].append((task_id, status))

    async def fake_set_chat_allowlist(_app: Any, chat_id: str, *, is_allowed: bool) -> None:
        state["allowlist_updates"].append((chat_id, is_allowed))

    async def fake_set_person_blocked(_app: Any, person_id: str, *, blocked: bool) -> None:
        state["person_block_updates"].append((person_id, blocked))

    async def fake_update_person_annotations(
        _app: Any,
        person_id: str,
        *,
        manual_tags: list[str],
        notes: str | None,
    ) -> None:
        state["person_annotation_updates"].append((person_id, manual_tags, notes))

    async def fake_update_owner_profile(
        _app: Any,
        *,
        context_tags: list[str],
        profile_notes: str | None,
        preferred_language: str,
    ) -> None:
        state["owner_profile_updates"].append((context_tags, profile_notes, preferred_language))

    async def fake_update_person_relationship_annotation(
        _app: Any,
        person_id: str,
        *,
        labels: list[str],
        note: str | None,
    ) -> None:
        state["relationship_annotation_updates"].append((person_id, labels, note))

    async def fake_update_chat_relationship_annotation(
        _app: Any,
        chat_id: str,
        *,
        labels: list[str],
        note: str | None,
    ) -> None:
        state["chat_relationship_annotation_updates"].append((chat_id, labels, note))

    async def fake_erase_person_cascade(
        _app: Any,
        person_id: str,
        *,
        actor: str,
    ) -> dict[str, Any]:
        state["person_erase_updates"].append((person_id, actor))
        return {
            "person_id": person_id,
            "display_name": "Ilyas",
            "target_hash": "hashed",
            "deleted": {"person": 1},
            "warnings": [],
        }

    monkeypatch.setattr(mcp_app, "get_analytics_overview_data", fake_overview)
    monkeypatch.setattr(mcp_app, "get_conversation_data", fake_conversations)
    monkeypatch.setattr(mcp_app, "get_open_tasks_data", fake_tasks)
    monkeypatch.setattr(mcp_app, "get_people_data", fake_people)
    monkeypatch.setattr(mcp_app, "get_chat_data", fake_chats)
    monkeypatch.setattr(mcp_app, "get_conversation_detail_data", fake_conversation_detail)
    monkeypatch.setattr(mcp_app, "get_person_detail_data", fake_person_detail)
    monkeypatch.setattr(mcp_app, "get_owner_profile_data", fake_owner_profile)
    monkeypatch.setattr(mcp_app, "get_chat_detail_data", fake_chat_detail)
    monkeypatch.setattr(mcp_app, "get_owner_person_id", lambda _app: mcp_app.asyncio.sleep(0, result="owner-1"))
    monkeypatch.setattr(mcp_app, "update_task_status", fake_update_task_status)
    monkeypatch.setattr(mcp_app, "set_chat_allowlist", fake_set_chat_allowlist)
    monkeypatch.setattr(mcp_app, "set_person_blocked", fake_set_person_blocked)
    monkeypatch.setattr(mcp_app, "update_person_annotations", fake_update_person_annotations)
    monkeypatch.setattr(mcp_app, "update_owner_profile", fake_update_owner_profile)
    monkeypatch.setattr(mcp_app, "update_person_relationship_annotation", fake_update_person_relationship_annotation)
    monkeypatch.setattr(mcp_app, "update_chat_relationship_annotation", fake_update_chat_relationship_annotation)
    monkeypatch.setattr(mcp_app, "erase_person_cascade", fake_erase_person_cascade)
    app = mcp_app.create_app(use_lifespan=False)
    app.state.jobs = {}
    return app, state


def test_analytics_redirects_to_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/analytics", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/admin"
    assert response.headers["cache-control"].startswith("no-store")


def test_root_redirects_to_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/admin"
    assert response.headers["cache-control"].startswith("no-store")


def test_admin_overview_renders_dashboard(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/admin")
    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("no-store")
    assert "Пульт" in response.text
    assert "Discussed rollout details." in response.text
    assert "Ship admin UI" in response.text


def test_admin_overview_uses_versioned_static_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/admin")
    assert response.status_code == 200
    assert "/static/admin.css?v=" in response.text
    assert 'http-equiv="Cache-Control"' in response.text


def test_admin_people_links_context(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/admin/people")
    assert response.status_code == 200
    assert "ilyasni" in response.text
    assert "коллега" in response.text
    assert "frontier" in response.text
    assert "/persons/person-1/context" in response.text
    assert "Блокировать" in response.text
    assert "раздел" in response.text
    assert "/admin/me" in response.text
    assert "Контекст" in response.text


def test_admin_me_renders_owner_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/admin/me")
    assert response.status_code == 200
    assert "Профиль владельца" in response.text
    assert "first-party" in response.text
    assert "Ilya" in response.text
    assert "Русский" in response.text
    assert "работа, pil" in response.text


def test_admin_me_post_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    app, state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/admin/me",
            data={
                "context_tags": "Работа, семья, pil",
                "profile_notes": "Держать summaries на русском.",
                "preferred_language": "ru",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/me?flash=owner_profile_saved"
    assert state["owner_profile_updates"] == [
        (["работа", "семья", "pil"], "Держать summaries на русском.", "ru")
    ]


def test_owner_person_route_redirects_to_admin_me(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _state = _build_app(monkeypatch)

    async def fake_owner_person_detail(_app: Any, person_id: str) -> dict[str, Any]:
        return {
            "person": {
                "id": person_id,
                "username": "ilyasni",
                "display_name": "Ilya",
                "last_interaction_at": "2026-05-14 08:20",
                "topics": [],
                "organizations": [],
                "manual_tags": [],
                "notes": None,
                "blocked": False,
                "is_owner": True,
            },
            "relationship_annotation": {
                "labels": [],
                "labels_preview": [],
                "labels_hidden_count": 0,
                "note": None,
            },
            "recent_windows": [],
            "tasks": [],
            "graph_neighbors": [],
            "semantic_memory": [],
            "graph_neighbors_status": "ok",
            "semantic_memory_status": "ok",
        }

    monkeypatch.setattr(mcp_app, "get_person_detail_data", fake_owner_person_detail)
    with TestClient(app) as client:
        response = client.get("/admin/people/owner-1", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/admin/me"


def test_person_detail_shows_degraded_notices(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _state = _build_app(monkeypatch)

    async def fake_degraded_person_detail(_app: Any, person_id: str) -> dict[str, Any]:
        return {
            "person": {
                "id": person_id,
                "username": "ilyasni",
                "display_name": "Ilyas",
                "last_interaction_at": "2026-05-14 08:20",
                "topics": ["ops", "memory"],
                "organizations": ["PIL"],
                "manual_tags": ["коллега"],
                "notes": None,
                "blocked": False,
            },
            "relationship_annotation": {
                "labels": ["коллега"],
                "labels_preview": ["коллега"],
                "labels_hidden_count": 0,
                "note": None,
            },
            "recent_windows": [],
            "tasks": [],
            "graph_neighbors": [],
            "semantic_memory": [],
            "graph_neighbors_status": "graph_neighbors_timeout",
            "semantic_memory_status": "semantic_memory_timeout",
        }

    monkeypatch.setattr(mcp_app, "get_person_detail_data", fake_degraded_person_detail)
    with TestClient(app) as client:
        response = client.get("/admin/people/person-1")
    assert response.status_code == 200
    assert "Граф связей временно недоступен" in response.text
    assert "Семантическая память временно недоступна" in response.text


def test_conversation_detail_renders_messages_and_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/admin/conversations/window-1")
    assert response.status_code == 200
    assert "Need to ship admin UI." in response.text
    assert "Запустить повторную обработку" in response.text
    assert "responsiveness" in response.text


def test_task_status_post_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    app, state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/admin/tasks/task-1/status",
            data={"status": "done", "redirect_to": "/admin/tasks"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/tasks?flash=task_status_done"
    assert state["task_updates"] == [("task-1", "done")]


def test_chat_allowlist_post_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    app, state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/admin/chats/chat-1/allowlist",
            data={"redirect_to": "/admin/chats/chat-1"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/chats/chat-1?flash=chat_disallowed"
    assert state["allowlist_updates"] == [("chat-1", False)]


def test_admin_chats_renders_relationship_context(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/admin/chats")
    assert response.status_code == 200
    assert "Ops chat" in response.text
    assert "работа" in response.text
    assert "pil" in response.text
    assert "Контекст" in response.text


def test_chat_relationship_post_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    app, state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/admin/chats/chat-1/relationship",
            data={
                "relationship_labels": "Работа, pil, внутренний контур",
                "relationship_note": "Главный рабочий чат по сервису.",
                "redirect_to": "/admin/chats/chat-1",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/chats/chat-1?flash=relationship_annotation_saved"
    assert state["chat_relationship_annotation_updates"] == [
        ("chat-1", ["работа", "pil", "внутренний контур"], "Главный рабочий чат по сервису.")
    ]


def test_person_block_post_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    app, state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/admin/people/person-1/block",
            data={"redirect_to": "/admin/people/person-1"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/people/person-1?flash=person_blocked"
    assert state["person_block_updates"] == [("person-1", True)]


def test_person_annotations_post_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    app, state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/admin/people/person-1/annotations",
            data={
                "manual_tags": "Коллега, pet-проект, семья",
                "notes": "Лучше писать вечером.",
                "redirect_to": "/admin/people/person-1",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/people/person-1?flash=person_annotations_saved"
    assert state["person_annotation_updates"] == [
        ("person-1", ["коллега", "pet-проект", "семья"], "Лучше писать вечером.")
    ]


def test_person_erase_post_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    app, state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/admin/people/person-1/erase",
            data={"redirect_to": "/admin/people"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/people?flash=person_erased"
    assert state["person_erase_updates"] == [("person-1", "ui:owner")]


def test_person_relationship_post_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    app, state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/admin/people/person-1/relationship",
            data={
                "relationship_labels": "Коллега, frontier, работа",
                "relationship_note": "Основной рабочий контакт.",
                "redirect_to": "/admin/people/person-1",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/people/person-1?flash=relationship_annotation_saved"
    assert state["relationship_annotation_updates"] == [
        ("person-1", ["коллега", "frontier", "работа"], "Основной рабочий контакт.")
    ]


def test_person_erase_api_queues_job(monkeypatch: pytest.MonkeyPatch) -> None:
    app, state = _build_app(monkeypatch)

    async def fake_validate_person(_app: Any, person_id: str) -> dict[str, Any]:
        return {"id": person_id, "display_name": "Ilyas", "tg_user_id": 77, "is_owner": False}

    monkeypatch.setattr(mcp_app, "_validate_person_erase_target", fake_validate_person)

    with TestClient(app) as client:
        response = client.post("/persons/person-1/erase")
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        job_response = client.get(f"/jobs/{job_id}")

    assert response.headers["location"] == f"/jobs/{job_id}"
    assert job_response.status_code == 200
    assert job_response.json()["status"] == "done"
    assert state["person_erase_updates"] == [("person-1", "system")]


def test_owner_annotations_post_redirects_to_admin_me(monkeypatch: pytest.MonkeyPatch) -> None:
    app, state = _build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/admin/people/owner-1/annotations",
            data={
                "manual_tags": "работа",
                "notes": "test",
                "redirect_to": "/admin/people/owner-1",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/me?flash=owner_profile_readonly"
    assert state["person_annotation_updates"] == []


def test_person_detail_progressive_disclosure_helpers() -> None:
    preview, hidden = mcp_app._list_preview(["one", "two", "three", "four"], limit=2)
    assert preview == ["one", "two"]
    assert hidden == 2

    semantic_preview = mcp_app._semantic_memory_preview_items(
        [{"kind": "analysis_window", "summary": "x" * 260, "window_id": "window-1"}]
    )
    assert semantic_preview[0]["kind"] == "analysis_window"
    assert semantic_preview[0]["window_id"] == "window-1"
    assert semantic_preview[0]["summary"].endswith("…")


def test_await_with_timeout_uses_fallback_on_timeout() -> None:
    async def slow() -> str:
        await mcp_app.asyncio.sleep(0.02)
        return "slow"

    result, status = mcp_app.asyncio.run(
        mcp_app._await_with_timeout(
            slow(),
            timeout_s=0.001,
            fallback=[],
            status_name="semantic_memory",
        )
    )

    assert result == []
    assert status == "semantic_memory_timeout"
