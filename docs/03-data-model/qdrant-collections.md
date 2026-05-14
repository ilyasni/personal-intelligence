# Qdrant collections

> Документ частично описывает pre-reset схему.
> В новой архитектуре embeddings управляются через `embedding-indexer` и profile-aware collection aliases; см. [../02-architecture/ai-integrated-architecture.md](../02-architecture/ai-integrated-architecture.md).

Qdrant хранит embeddings для семантического retrieval.

## Принципы

- **Embedding model — конфигурируется per collection.** Дефолт — `bge-m3` (мультиязычная, 1024-dim, MIT-friendly).
- **Payload — обязательно структурирован.** Без свободных полей; payload-индексы — в этом документе.
- **Идемпотентность — по `chunk_id` (UUID, тот же, что в Postgres если применимо).**
- **Удаление каскадом.** На GDPR-erase `services/maintenance` выполняет `delete by filter` (`payload.person_ids` contains `X`).

## Collections

### `memory_chunks`

Долгосрочная семантическая память.

| Параметр   | Значение                  |
|------------|---------------------------|
| size       | 1024                      |
| distance   | Cosine                    |
| on_disk    | true (vectors), false (payload) |
| hnsw m     | 16                        |
| hnsw ef    | 128                       |

Payload schema:
```json
{
  "chunk_id": "uuid",
  "type": "summary | note | quote | fact",
  "text": "string (text used for embedding)",
  "person_ids": ["uuid"],
  "chat_id": "uuid|null",
  "topic_slugs": ["string"],
  "language": "ru|en|...",
  "source": {
    "kind": "message|interaction|external",
    "tg_chat_id": 0,
    "tg_message_id": 0,
    "interaction_id": "uuid|null"
  },
  "created_at": "iso8601",
  "weight": 1.0,
  "schema_version": 1
}
```

Payload indices:
- `person_ids` — keyword
- `chat_id` — keyword
- `topic_slugs` — keyword
- `created_at` — datetime
- `type` — keyword

### `person_summaries`

Embedding профиля контакта целиком (синтезируется persona-builder из связки tone/topics/notes). Используется для запросов «кто из моих контактов похож на X?» / «найди контактов с похожим стилем».

| Параметр | Значение |
|----------|----------|
| size     | 1024     |
| distance | Cosine   |

Payload:
```json
{
  "person_id": "uuid",
  "display_name": "string",
  "topics": ["string"],
  "communication_style": "string",
  "role": "string|null",
  "schema_version": 1
}
```

### `interaction_summaries`

Embedding каждого Interaction (для семантического поиска «когда мы обсуждали X»).

| Параметр | Значение |
|----------|----------|
| size     | 1024     |
| distance | Cosine   |

Payload:
```json
{
  "interaction_id": "uuid",
  "chat_id": "uuid",
  "participants": ["uuid"],
  "topics": ["string"],
  "window_start": "iso8601",
  "window_end": "iso8601",
  "schema_version": 1
}
```

## Типичные запросы

«Top-5 семантически близких чанков для запроса `q` про person X»:
```python
qdrant.search(
    collection="memory_chunks",
    query_vector=embed(q),
    query_filter=Filter(must=[FieldCondition(key="person_ids", match=MatchAny(any=[X]))]),
    limit=5,
    with_payload=True,
)
```

«Все чанки про person X, отсортированные по дате»:
```python
qdrant.scroll(
    collection="memory_chunks",
    scroll_filter=Filter(must=[FieldCondition(key="person_ids", match=MatchAny(any=[X]))]),
    order_by={"key": "created_at", "direction": "desc"},
    limit=100,
)
```

«Hybrid search» (вектор + payload):
```python
qdrant.search(
    collection="memory_chunks",
    query_vector=embed(q),
    query_filter=Filter(
        must=[FieldCondition(key="topic_slugs", match=MatchAny(any=["ai","design"]))],
        must_not=[FieldCondition(key="type", match=MatchValue(value="quote"))]
    ),
    limit=10,
)
```

## Управление моделями embeddings

- Текущая модель и её ревизия — в `setting.embedding.model = 'bge-m3@v1'`.
- При смене модели:
  1. Создать новую collection с суффиксом версии (`memory_chunks_v2`).
  2. `services/maintenance` запускает backfill через `services/memory-distiller` в режиме re-embed.
  3. После завершения — `setting.embedding.collection = 'memory_chunks_v2'`.
  4. Через 7 дней — удалить старую collection.

## Размеры (оценки)

- `memory_chunks`: ~5 чанков × 4 КБ payload × N сообщений. На 100К сообщений ~500К чанков ~2 ГБ.
- На SSD с `on_disk=true` это терпимо. Periodic snapshot — раз в сутки в backup/object storage.

## Открытые вопросы

- Q-QDR-1. Переехать на pgvector в MVP-3, чтобы не держать Qdrant отдельно? — см. ADR-0004.
- Q-QDR-2. Делать ли отдельную collection под short-term memory с быстрым TTL (например, 7 дней)?
