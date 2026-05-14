# MCP API

MCP-сервер — единый интерфейс, через который внешние LLM получают контекст.

## Транспорт

- Сервер реализован в `services/mcp-rest-api` поверх `FastMCP` (или эквивалентного SDK).
- Транспорт — HTTP+SSE и stdio (для локальной интеграции через Claude Desktop / Claude Code).
- Auth: API-key (header `Authorization: Bearer <key>`) → проверяется по `api_key`.
- Все обращения логируются в `audit_log`.

## Инструменты (tools)

Все инструменты возвращают JSON, готовый к подаче в LLM. Поля стабильны (snake_case).

### `get_person`

Получить базовый профиль контакта.

```
input:
  person_id?: string         # UUID PIL
  tg_user_id?: integer       # альтернативный ключ
  username?: string          # альтернативный ключ
output:
  person: Person
```

Возвращает `Person` (см. [docs/03-data-model/postgres-schema.md](../03-data-model/postgres-schema.md#person)).

### `search_persons`

Полнотекстовый + tag/topic поиск.

```
input:
  q?: string                 # текст
  topics?: string[]
  organization?: string
  limit?: integer (default 20)
output:
  hits: [{ person: Person, score: float }]
```

### `get_person_context`

Главный инструмент. Композит из persona + recent interactions + open tasks + graph + memory.

```
input:
  person_id: string
  query?: string             # тематический фокус
  hops?: integer (default 1) # глубина графа
  k_memory?: integer (default 5)
output:
  person: Person
  graph: {
    neighbors: [Person & { relation, weight }],
    chats_in_common: [Chat]
  }
  recent_interactions: [Interaction]
  open_tasks: [Task]
  memory: [MemoryChunk]
  context_markdown: string   # удобный для прямой подачи в LLM
```

### `get_open_tasks`

```
input:
  person_id?: string
  due_before?: iso8601
  limit?: integer (default 50)
output:
  tasks: [Task]
```

### `search_interactions`

```
input:
  q: string
  person_id?: string
  chat_id?: string
  from?: iso8601
  to?: iso8601
  limit?: integer (default 20)
output:
  hits: [{ interaction: Interaction, score: float }]
```

### `search_memory`

Сырая семантика над `memory_chunks`.

```
input:
  q: string
  person_id?: string
  topic?: string
  type?: "summary"|"note"|"quote"|"fact"
  limit?: integer (default 10)
output:
  hits: [{ chunk: MemoryChunk, score: float }]
```

### `graph_walk`

```
input:
  start_person_id: string
  hops: integer (1..3)
  rel_types?: string[]       # ["MENTIONS","CO_CHAT","KNOWS"]
output:
  nodes: [Person | Organization | Chat | Topic]
  edges: [{ from, to, type, weight }]
```

### `who_works_at`

```
input:
  org_slug: string
output:
  people: [{ person: Person, role: string, since: iso8601 }]
```

### `recall_with_query`

GraphRAG-композитор по свободному вопросу — для случаев «лень структурировать запрос».

```
input:
  query: string
  scope?: { person_ids?: [string], chat_ids?: [string], from?: iso8601, to?: iso8601 }
  budget?: { max_chunks?: int, max_hops?: int }
output:
  answer_markdown: string
  citations: [{ kind: "person"|"interaction"|"memory"|"task", id: string, ref: string }]
```

### Mutations

В MCP мутации запрещены по умолчанию. Включаются API-key scope-ом `mutate`:

- `mark_task_done(task_id)`
- `note_about_person(person_id, text)` — создаёт `memory_chunk` типа `note`.

Опасные действия (erase) выставляются только в REST для UI (см. [rest-api.md](rest-api.md)).

## Quotas и rate-limits

- Дефолт: 60 запросов/мин на api-key.
- Большие операции (`graph_walk hops=3`, `recall_with_query`) — token-bucket с весом 5.

## Ошибки

Общий формат:
```json
{ "error": { "code": "not_found|invalid|forbidden|rate_limited|partial|server", "message": "...", "details": {} } }
```
`partial` возвращается, когда часть бэкенда недоступна (например, Qdrant offline) — в payload приходит то, что удалось собрать, с пометкой.

## Версионирование

MCP-инструменты следуют API-версии (`/v1/mcp`). Tools имеют `version` в метаданных. При breaking — выпускаем `_v2`-инструмент, старый остаётся deprecated 90 дней.

## Тестирование

- Каждый tool имеет contract-test против golden-fixture.
- Smoke-MCP клиент в `scripts/dev/mcp_probe.py` гоняет все инструменты на seed-данных.
- Интеграционный тест через `mcp-inspector` (если применимо).
