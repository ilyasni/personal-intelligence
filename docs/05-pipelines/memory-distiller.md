# Pipeline: Memory Distiller

> Этот документ отражает pre-reset design.
> В актуальной target-архитектуре роль `memory-distiller` заменена на `embedding-indexer`; см. [../02-architecture/ai-integrated-architecture.md](../02-architecture/ai-integrated-architecture.md).

`services/memory-distiller` — формирует долгосрочную семантическую память: chunks + embeddings.

## Цель

Закладывать в Qdrant compact «memories» — summary, заметки, факты — чтобы retrieval мог отвечать на свободные вопросы про прошлое.

## Источники

- `events.processing.interaction_updated` → создаём `memory_chunk` типа `summary`.
- `events.processing.task_created` / `task_resolved` → `memory_chunk` типа `fact`.
- `events.processing.entity_found` с organization+role и confidence ≥ 0.9 → `fact` («Алексей работает в X»).
- Ручные заметки через API `POST /v1/memory/note` → `note`.
- Quotes — короткие цитаты-сэмплы (для tone recall) — типа `quote`. Создаются собственным эвристическим селектором (1 раз в сутки, top-5 «характерных» фраз каждого Person).

## Алгоритм

1. Принять событие → нормализовать в `MemoryChunk` (см. схему `qdrant-collections.md`).
2. Рассчитать embedding через `libs/llm-client.embeddings` (модель из настройки, дефолт `bge-m3`).
3. UPSERT в Qdrant collection `memory_chunks` с payload и vector.
4. Опубликовать `events.processing.memory_chunk_ready` (для аудита и UI).

## Дедупликация

- Считаем `simhash` от текста + `person_ids` множества → если уже есть chunk с похожим simhash за последние 30 дней → объединяем (поднимаем `weight`, обновляем `last_at`).

## Re-embed

- При смене `setting.embedding.model` `services/maintenance` гонит batch-re-embed (см. `qdrant-collections.md`).
- Распараллеливается через consumer-группы.

## Конфигурация

```
MEMORY_EMBEDDING_MODEL=bge-m3
MEMORY_EMBEDDING_DIM=1024
MEMORY_DEDUP_WINDOW_DAYS=30
MEMORY_QUOTE_GENERATION_CRON=0 4 * * *
MEMORY_LLM_MODE=local|cloud|hybrid
```

## Observability

- `pil_memory_chunks_total{type}`
- `pil_memory_embed_latency_ms{model}` (histogram)
- `pil_memory_dedup_hits_total`

## Тесты

- Unit — конверсия события в chunk, simhash, normalize text.
- Snapshot — на 50 событий → ожидаемое число chunks.
- Integration — Qdrant testcontainers + проверка vector-distance в типовых сценариях.

## Open questions

- Q-MEM-1. Использовать ли late chunking (большой контекст → разбить на short-spans c вектором) — улучшает retrieval.
- Q-MEM-2. Делать ли cross-encoder reranking для top-K в MCP `recall_with_query`?
