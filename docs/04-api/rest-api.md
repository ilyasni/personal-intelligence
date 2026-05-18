# REST API

REST-эндпоинты обслуживают Admin UI и внутренние интеграции. Полная спека — [openapi.yaml](openapi.yaml).

## Базовый URL

`https://pil.local/api/v1/` (через Caddy reverse-proxy). В docker compose — `http://api:8080/v1/`.

## Аутентификация

- **UI**: JWT (Auth-Cookie HttpOnly) после логина Owner-а.
- **MCP-клиенты**: REST-эндпоинты `/v1/mcp/*` дублируют MCP-инструменты, защищены API-key (`Authorization: Bearer ...`).

## Группы эндпоинтов

### `/v1/connections`
- `GET /v1/connections` — список подключений.
- `POST /v1/connections/business-bot` — настроить Business Bot токен.
- `POST /v1/connections/telethon/start` — начать сессию (возвращает QR/код).
- `POST /v1/connections/telethon/confirm` — подтвердить (передать 2FA).
- `DELETE /v1/connections/{id}` — отключить.

### `/v1/allowlist`
- `GET /v1/allowlist/chats?q=&page=` — список чатов с флагом `is_allowed`.
- `PATCH /v1/allowlist/chats/{chat_id}` — `{ allowed: bool }`.
- `GET /v1/allowlist/persons?q=` — список контактов.
- `PATCH /v1/allowlist/persons/{person_id}` — `{ allowed: bool, blocked: bool }`.

### `/v1/persons`
- `GET /v1/persons?q=&topic=&org=&page=` — поиск.
- `GET /v1/persons/{id}` — карточка (включая агрегаты).
- `PATCH /v1/persons/{id}` — апдейт notes / tags / topics (вручную).
- `GET /v1/persons/{id}/context?query=&hops=` — то же, что MCP `get_person_context`.
- `GET /v1/persons/{id}/brief` — grounded synthesis brief с `summary`, `confidence`, `evidence_window_ids`, `evidence_message_ids`, `caveats`.
- `GET /v1/persons/{id}/export` — zip-экспорт.
- `DELETE /v1/persons/{id}/erase` — GDPR-каскадное удаление (async, возвращает job id).
- Текущий runtime также поддерживает совместимый `POST /persons/{id}/erase` и `GET /jobs/{job_id}` без version-prefix, потому что server-rendered admin сейчас работает поверх unprefixed FastAPI routes.

### `/v1/tasks`
- `GET /v1/tasks?status=open&due_before=` — список.
- `POST /v1/tasks` — ручное создание.
- `PATCH /v1/tasks/{id}` — поменять status, due, description.
- `DELETE /v1/tasks/{id}`.

### `/v1/interactions`
- `GET /v1/interactions?chat_id=&q=&from=&to=&page=`
- `GET /v1/interactions/{id}` — включая ссылку на raw window (object key).

### `/v1/memory`
- `POST /v1/memory/search` — то же, что MCP `search_memory`.
- `POST /v1/memory/recall` — то же, что MCP `recall_with_query`.

### `/v1/graph`
- `GET /v1/graph/walk?start=&hops=&types=`
- `GET /v1/graph/path?a=&b=&max_hops=3`

### `/v1/settings`
- `GET /v1/settings` — все.
- `PATCH /v1/settings` — patch объекта (`{retention.raw_message_days: 60, llm.mode.entity: 'local'}`).
- `GET /v1/settings/api-keys`
- `POST /v1/settings/api-keys` — `{name, scopes[]}` → возвращает ключ единожды.
- `DELETE /v1/settings/api-keys/{id}`.

### `/v1/system`
- `GET /v1/system/health` — статус сервисов и БД.
- `GET /v1/system/queues` — длина потоков и DLQ.
- `GET /v1/system/queues/{stream}/dlq` — содержимое DLQ.
- `POST /v1/system/queues/{stream}/dlq/{event_id}/retry` — переотправить.
- `POST /v1/system/commands` — отправить `system.command` событие (см. event-schema).

### `/v1/audit`
- `GET /v1/audit?from=&to=&actor=&action=&page=`

## Конвенции

- Pagination — cursor-based (`?cursor=&limit=`). Возврат `next_cursor` в meta.
- Сортировка — `?sort=field,-otherfield`.
- ETag для GET-карточек.
- ProblemDetails (RFC 9457) для ошибок:
```json
{ "type": "/errors/not-found", "title": "Person not found", "status": 404, "detail": "id=...", "instance": "/v1/persons/..." }
```
- CORS: только из домена Admin UI.
- CSRF: stateful (Sec-Fetch-* checks) — для UI; API-key endpoints — stateless.

## Idempotency

Мутирующие эндпоинты принимают `Idempotency-Key` (UUID): результат кешируется 24ч.

## Долгие операции

- `POST /v1/persons/{id}/erase` → `202 Accepted` + `Location: /v1/jobs/{job_id}`.
- `GET /v1/jobs/{job_id}` → статус (`queued`, `running`, `done`, `failed`), прогресс, результат.
- В текущем baseline job-store хранится в памяти процесса `mcp-rest-api`; это подходит для single-owner self-host runtime, но durable queue/job persistence остаётся следующим шагом hardening.

## OpenAPI

Полный контракт — [openapi.yaml](openapi.yaml). Файл генерируется из FastAPI (`python -m services.mcp_rest_api.export_openapi`) при каждом релизе.

## Grounded synthesis notes

- `brief` не является свободным agent endpoint.
- Сначала собирается deterministic context из Postgres/Qdrant/Neo4j.
- Wormsoft используется только для короткого synthesis поверх уже собранных фактов.
- Если провайдер недоступен, runtime возвращает русский heuristic fallback с caveat `heuristic fallback`.
