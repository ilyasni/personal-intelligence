# Компоненты системы

Этот файл фиксирует **финальные сервисные границы**, вокруг которых дальше должен перестраиваться код и roadmap.

> Актуализация на 2026-05-13.
> Если текущий `services/` каталог ещё не совпадает с этим документом, это считается переходным состоянием.

## Целевая сервисная карта

### `services/telegram-ingestor`

- **Роль.** Единая точка входа для Telegram updates.
- **Читает.** Telegram messages, edits, deletes, media, business events.
- **Пишет.** `events.telegram.*` в Redis Streams; raw payload и media в S3.
- **LLM.** Не использует.

### `services/ai-orchestrator`

- **Роль.** Главный AI runtime сервиса.
- **Читает.** `events.telegram.message`, `events.telegram.edit`, interaction windows и локальный context из Postgres.
- **Делает.**
  - fact extraction;
  - task extraction;
  - interaction summarization;
  - persona update derivation;
  - provider routing по task family.
- **Пишет.** Только projection commands и orchestration events.
- **LLM.** Да, через Wormsoft / Polza и LangGraph workflow.

### `services/memory-projector`

- **Роль.** Детерминированно применяет projection commands.
- **Читает.** `events.memory.*` / projection commands.
- **Пишет.**
  - Postgres canonical state;
  - Neo4j relationships;
  - S3 artifacts.
- **LLM.** Не использует.

### `services/embedding-indexer`

- **Роль.** Индексация памяти в Qdrant.
- **Читает.** Projection commands на индексацию и reindex jobs.
- **Пишет.** Dense/hybrid points в Qdrant.
- **LLM.** Да, но только embedding endpoints.

### `services/mcp-rest-api`

- **Роль.** Внешний retrieval и tool interface.
- **Читает.** Postgres, Qdrant, Neo4j, S3.
- **Пишет.** Audit log, optional cache entries.
- **LLM.** Опционально для grounded synthesis, но не как основной способ retrieval.

### `services/maintenance`

- **Роль.** Background operations.
- **Делает.**
  - partitions;
  - retention;
  - erase cascade jobs;
  - controlled reindex;
  - embedding profile switch workflows.
- **LLM.** Не использует.

## Внутренние библиотеки

### `libs/contracts`

- Pydantic-модели событий, projection commands и API payloads.
- Любое изменение требует ADR и version bump.

### `libs/llm-router`

- Унифицированный routing layer для task families.
- Должен вобрать практики из `frontier-intelligence`:
  - provider policy;
  - fallback chain;
  - circuit/budget/quota separation;
  - routing events;
  - shadow mode.

### `libs/prompt-registry`

- Версионированные system prompts и output schemas.
- Один prompt family на один use case.

### `libs/retrieval`

- SQL + Qdrant + Neo4j retrieval composer.
- Планировщик retrieval path:
  - SQL only;
  - SQL + vector;
  - SQL + vector + graph.

### `libs/storage-clients`

- Обёртки вокруг Postgres, Neo4j, Qdrant и S3 с retry/metrics.

### `libs/observability`

- Метрики, structured logging, traces.
- Должен покрывать не только infra, но и routing/orchestration decisions.

## Переходное состояние текущих сервисов

### `entity-extractor`

- **Статус.** Transitional runtime component.
- **Цель.** Логика переносится в `ai-orchestrator`.

### `persona-builder`

- **Статус.** Transitional runtime component.
- **Цель.** Persona derivation становится output-веткой `ai-orchestrator`, а запись — задачей `memory-projector`.

### `task-extractor`

- **Статус.** Transitional runtime component.
- **Цель.** Переходит в `ai-orchestrator`.

### `chat-summarizer`

- **Статус.** Transitional runtime component.
- **Цель.** Переходит в `ai-orchestrator`.

## Почему итоговая структура именно такая

1. Ingestion остаётся простым и deterministic.
2. Весь LLM complexity собирается в одном orchestration слое.
3. Persistence отделяется от inference.
4. Embeddings получают свой lifecycle и profile management.
5. API не превращается в "второго агента", а остаётся grounded retrieval boundary.

## Что это значит для каталога `services/`

Долгосрочно `services/` должен выглядеть так:

- `telegram-ingestor`
- `ai-orchestrator`
- `memory-projector`
- `embedding-indexer`
- `mcp-rest-api`
- `maintenance`
- `xray`

Остальные processing-сервисы считаются временной совместимостью до миграции логики в новую схему.
