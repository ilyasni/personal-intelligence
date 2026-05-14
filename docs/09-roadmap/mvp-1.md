# MVP-1: ядро сбора

> Актуализация на 2026-05-12. Этот документ остаётся roadmap-спеком, но фактический прогресс смотри в `milestones.md`. С момента написания появились расхождения: в runtime уже есть Neo4j/Qdrant и S3 cloud.ru, а UI/API-слой ещё не реализован.

**Цель**. Доказать, что PIL может собирать содержимое разрешённых чатов и превращать его в полезную структурированную память (Persons, Tasks, Interactions), доступную через MCP.

**Ожидаемая длительность**: 8–10 недель параллельной работы (один Owner + три агента).

## Scope

В:
- Telethon userbot + (опц.) Business Bot adapter.
- Postgres-схема: connection, chat, person, chat_membership, interaction (без партиций), task, mention, processed_event, audit_log, api_key, setting.
- Redis Streams + DLQ.
- Extractors: entity (rule + simple LLM), persona (эвристика), task (rule).
- Chat summarizer (эвристика, без LLM).
- MCP API инструменты: `get_person`, `search_persons`, `get_person_context` (без graph, без memory), `get_open_tasks`, `search_interactions`.
- REST API + минимальная авторизация (JWT + один API-key).
- Admin UI: Connections, Allowlist, Persons (list + card), Tasks list, Settings (минимум).
- Docker Compose + Caddy + Prometheus/Grafana.
- Basic backup/restore.

Не в:
- Neo4j, Qdrant, GraphRAG.
- LLM-улучшенный summarizer.
- Caсcading erase (минимальный, без всех индексов — Postgres CASCADE достаточно).
- Multi-account.
- Speech-to-text.
- Visual graph в UI.

## Тикеты по слоям

(Можно брать любым агентом; в скобках — рекомендация на основе сильных сторон, но любой может выполнить.)

### Layer A — фундамент (1–2 неделя)
- A-01. Monorepo init: poetry, ruff, mypy, pre-commit, Makefile, базовые services skeleton. (Codex — большой объём шаблонного кода.)
- A-02. `libs/contracts` с базовыми события `telegram.message`, `telegram.business_connection`, `processing.entity_found`, `processing.task_created`, `processing.interaction_updated`. (Claude Code — сквозной контракт.)
- A-03. `libs/observability` — structlog + prometheus client. (Codex.)
- A-04. `libs/storage-clients` — Postgres (asyncpg + SQLAlchemy), Redis. (Codex.)
- A-05. Docker Compose stack (postgres, redis, minio, caddy, prometheus, grafana, loki, promtail). (Codex.)
- A-06. CI pipeline (.github/workflows/ci.yml) с lint + unit + integration testcontainers. (Codex.)
- A-07. ADR-0001 (architecture decisions) + наполнение ADR-0002..0006. (Claude Code.)

### Layer B — данные (2–3 неделя)
- B-01. Alembic init + миграции до person/chat/connection. (Codex.)
- B-02. Миграции для interaction (без партиционирования сначала), task, mention. (Codex.)
- B-03. Seed/fixtures: persons, chats, messages. `scripts/dev/gen_fixtures.py`. (Codex.)
- B-04. `services/maintenance` baseline (apscheduler), партиции для processed_event/audit_log. (Codex.)

### Layer C — ingestion (3–4 неделя)
- C-01. `services/telegram-ingestor` — Telethon login flow + минимум публикация в Redis. (Claude Code — много сквозного знания о Telethon.)
- C-02. Allowlist filter + сохранение raw в S3-compatible object storage. (Claude Code.)
- C-03. Business Bot adapter (webhook). (Claude Code.)
- C-04. Backfill chat command (consumer `system.command`). (Claude Code.)

### Layer D — processing (4–6 неделя)
- D-01. `services/entity-extractor` (spaCy rule-based). (Claude Code.)
- D-02. `services/persona-builder` (эвристика). (Claude Code.)
- D-03. `services/task-extractor` (rule + dateparser). (Claude Code.)
- D-04. `services/chat-summarizer` (эвристический, by_count strategy). (Claude Code.)
- D-05. Integration tests: event → Person/Task/Interaction. (Codex может писать массу тестов.)

### Layer E — API & UI (6–8 неделя)
- E-01. `services/mcp-rest-api` skeleton (FastAPI + auth + JWT login). (Cursor — интерактивно вытачиваем endpoints.)
- E-02. REST endpoints: `/persons`, `/persons/{id}`, `/persons/{id}/context (no graph/memory)`, `/tasks`, `/allowlist/*`, `/connections/*`, `/system/health`, `/system/queues`. (Cursor + Codex для тестов.)
- E-03. MCP server inside `services/mcp-rest-api` с инструментами `get_person`, `get_person_context`, `get_open_tasks`. (Claude Code.)
- E-04. Admin UI skeleton (Vite + Tailwind + router + auth flow). (Cursor.)
- E-05. Admin UI: Connections page + Allowlist page. (Cursor.)
- E-06. Admin UI: Persons list + Person card (Overview + Tasks + Interactions tabs). (Cursor.)
- E-07. Admin UI: Settings минимум (LLM mode, API keys management). (Cursor.)
- E-08. Admin UI: Dashboard cards + Queues page. (Cursor.)
- E-09. Audit log writes на каждый чтение MCP. (Codex.)
- E-10. Cascade erase endpoint (Postgres-only, без Neo4j/Qdrant — они в MVP-2). (Codex.)

### Layer F — quality & release (8–10 неделя)
- F-01. E2E Playwright по flows 1–4, 5, 6 (без graph), 8, 9. (Cursor.)
- F-02. Smoke (`make smoke`). (Codex.)
- F-03. Процедура snapshot/restore для текущего server runtime; `make`-обёртки допустимы, но не обязательны. (Codex.)
- F-04. Privacy pre-release checklist пройдён. (Claude Code — сквозной контроль.)
- F-05. Документация обновлена под фактическое поведение. (Любой агент.)

## Acceptance criteria

- [ ] Owner подключает Telethon userbot и/или Business Bot через UI.
- [ ] Allowlist редактируется; чаты вне него игнорируются.
- [ ] За 24 часа эксплуатации на реальных чатах в Postgres появляются ≥ 50 Persons, ≥ 20 Tasks, ≥ 100 Interactions (на типовой нагрузке).
- [ ] `GET /v1/persons/{id}/context` возвращает осмысленный JSON.
- [ ] MCP-инструменты доступны через API-key и логируются в audit.
- [ ] Удаление Person через UI — каскад в Postgres.
- [ ] Backup срабатывает по расписанию и restore-drill отрабатывает.
- [ ] CI зелёный, `make verify` < 10 минут.

## Известные риски

- LLM-зависимости пока минимальны (эвристика), качество summary и tasks будет грубоватым → ОК на MVP-1, цель — fix в MVP-2.
- Telethon FloodWait при больших backfill — лимитируем через `BACKFILL_RATE_LIMIT`.
- Reconciliation persons между сообщениями может давать дубликаты → плановое merge-UI в MVP-2.

## Что НЕ делаем в MVP-1 (явно)

- Neo4j / Qdrant.
- Visual graph.
- Proactive reminders.
- Audio/video.
- Мульти-аккаунт.
- Kubernetes.
