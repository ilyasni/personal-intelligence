# Event schema

> Этот контракт будет постепенно выравниваться под новую схему `ai-orchestrator` / `memory-projector` / `embedding-indexer`.
> До завершения миграции считайте [../02-architecture/ai-integrated-architecture.md](../02-architecture/ai-integrated-architecture.md) каноническим описанием целевых сервисных границ.

Все сервисы общаются через Redis Streams. Этот документ — контракт. Изменение поля = бамп `schema_version` + ADR (если поле обязательно).

## Имена потоков

| Stream                                | Producer           | Consumers                                  |
|---------------------------------------|--------------------|---------------------------------------------|
| `events.telegram.message`             | telegram-ingestor  | entity, persona, task, summarizer, memory, graph |
| `events.telegram.message_edited`      | telegram-ingestor  | entity, persona, task, summarizer, memory, graph |
| `events.telegram.message_deleted`     | telegram-ingestor  | summarizer, graph, maintenance              |
| `events.telegram.business_connection` | telegram-ingestor  | api, maintenance, ui                        |
| `events.processing.entity_found`      | entity-extractor   | persona, graph                              |
| `events.processing.task_created`      | task-extractor     | api, graph, ui                              |
| `events.processing.task_resolved`     | task-extractor     | api, graph, ui                              |
| `events.processing.interaction_updated`| chat-summarizer   | memory, graph, ui                           |
| `events.processing.memory_chunk_ready`| memory-distiller   | (только для аудита)                         |
| `events.system.command`               | api                | ingestor, maintenance                       |
| `<stream>:dlq`                        | любой consumer     | runbook handler                             |

Каждое имя потока — фиксированное.

## Базовый envelope

Каждое событие — JSON-объект со стандартным заголовком + payload.

```json
{
  "envelope": {
    "event_id": "01HXXXXXX",                          // ULID, уникальный
    "schema_version": 1,
    "type": "telegram.message",
    "trace_id": "uuid",                                // для observability
    "occurred_at": "2026-05-11T13:14:15.123Z",
    "ingested_at": "2026-05-11T13:14:15.456Z",
    "producer": "telegram-ingestor@1.2.3",
    "headers": {
      "language": "ru",
      "sensitivity": "default"
    }
  },
  "payload": { ... }
}
```

## Payload контракты

### `telegram.message`
```json
{
  "tg_chat_id": -1001234567890,
  "tg_message_id": 34567,
  "tg_from_user_id": 123456789,
  "tg_reply_to_message_id": 34560,
  "kind": "text|photo|voice|document|other",
  "text": "string|null",
  "media": [{"id": "uuid", "kind": "photo", "object_key": "raw-media/2026/05/11/.../id.jpg", "mime": "image/jpeg"}],
  "is_outgoing": false,
  "is_forward": false,
  "via_business_bot": false,
  "raw_object_key": "raw/2026/05/11/-1001234567890/34567.json"
}
```

### `telegram.message_edited`
Тот же payload + `edited_at`, `previous_text` (опц., если включён режим хранения истории редактирования).

### `telegram.message_deleted`
```json
{
  "tg_chat_id": -1001234567890,
  "tg_message_id": 34567,
  "deleted_at": "iso8601"
}
```

### `telegram.business_connection`
```json
{
  "business_connection_id": "string",
  "tg_user_id": 123456789,
  "status": "connected|disconnected",
  "allowed_chats": [-1001234567890, ...],
  "raw_object_key": "raw/business_connections/<id>.json"
}
```

### `processing.entity_found`
```json
{
  "source_event_id": "01HXXX",
  "tg_chat_id": -100...,
  "tg_message_id": 34567,
  "entities": [
    {"kind": "person", "surface": "Алексей Иванов", "person_id": "uuid|null", "confidence": 0.86},
    {"kind": "organization", "surface": "ООО Газпром", "slug": "gazprom", "confidence": 0.91},
    {"kind": "topic", "slug": "ai", "confidence": 0.7}
  ]
}
```

### `processing.task_created`
```json
{
  "task_id": "uuid",
  "title": "string",
  "owner_person_id": "uuid|null",
  "counterpart_person_id": "uuid|null",
  "due_at": "iso8601|null",
  "source_message_ref": {"tg_chat_id":..., "tg_message_id":...},
  "confidence": 0.7,
  "evidence": "цитата"
}
```

### `processing.task_resolved`
```json
{
  "task_id": "uuid",
  "resolution": "done|dropped",
  "evidence": "string|null"
}
```

### `processing.interaction_updated`
```json
{
  "interaction_id": "uuid",
  "chat_id": "uuid",
  "window_start": "iso8601",
  "window_end": "iso8601",
  "participants": ["uuid", ...],
  "topics": ["string"],
  "sentiment": "positive|negative|neutral|mixed",
  "summary": "string",
  "task_ids": ["uuid", ...]
}
```

### `processing.memory_chunk_ready`
```json
{
  "chunk_id": "uuid",
  "type": "summary|note|quote|fact",
  "person_ids": ["uuid"],
  "chat_id": "uuid|null",
  "vector_collection": "memory_chunks",
  "ts": "iso8601"
}
```

### `system.command`
Имеет дискриминатор `command`:
```json
{
  "command": "backfill_chat|erase_person|recompute_persona|...",
  "args": { ... }
}
```

## Идемпотентность

- Каждый consumer перед обработкой `event_id` пишет:
  ```sql
  INSERT INTO processed_event(consumer_name, event_id) VALUES (...)
  ON CONFLICT DO NOTHING RETURNING true;
  ```
- Если вставка ничего не вернула — событие уже обработано, пропускаем.
- Этого достаточно для `at-least-once → effectively-once`.

## Ретраи и DLQ

- 5 попыток с экспоненциальным backoff (1s, 4s, 16s, 1m, 5m).
- При исчерпании — `XACK` основной поток + `XADD` в `<stream>:dlq` с полями `error`, `attempts`, `last_traceback_id`.
- DLQ разбирается оператором (см. `docs/07-operations/runbook.md`). Есть UI-страница «DLQ».

## Совместимость

- **Обратно совместимо.** Добавление поля — без бампа `schema_version`. Удаление поля или изменение типа — обязательный bump.
- **Старые события на новом коде.** Каждый consumer держит migration-path для предыдущих `schema_version` (по крайней мере на 1 назад).
- **Новые события на старом коде.** Старые consumer'ы пропускают неизвестные поля.

## Где живут контракты в коде

- `libs/contracts/python/` — pydantic-модели.
- `libs/contracts/json-schema/` — генерированный JSON Schema для проверки (для не-Python клиентов).
- `libs/contracts/openapi/components.yaml` — для OpenAPI references.

Регенерация — `make contracts`.

## Открытые вопросы

- Q-EVT-1. Перейти с Redis Streams на NATS JetStream при появлении мульти-пользовательских инсталляций? — ADR-0003.
- Q-EVT-2. Делать ли отдельный поток для медиа-сообщений (большие payload'ы)?
