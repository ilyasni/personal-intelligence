# ADR 0007: Единый AI-orchestrator с LangGraph и task-based multi-LLM routing

- Дата: 2026-05-13
- Статус: Accepted

## Контекст

Изначальный план PIL предполагал несколько независимых processing-сервисов:

- `entity-extractor`
- `persona-builder`
- `task-extractor`
- `chat-summarizer`
- позднее `memory-distiller`
- позднее `graph-builder`

Практика показала, что такой подход годится как старт, но плохо масштабируется для AI-first runtime:

- prompt-логика размазывается по разным сервисам;
- сложно централизованно управлять routing/fallback/budget;
- structured extraction и summarization начинают дублировать друг друга;
- API-слой рискует превратиться в второй неуправляемый AI runtime.

Параллельно соседний проект `frontier-intelligence` уже подтвердил полезность:

- task-family routing;
- provider policy;
- guard/circuit/budget separation;
- shadow rollout;
- расширенной observability для LLM слоя.

## Варианты

**A. Оставить отдельные extractor-сервисы и просто добавить в каждый LLM-клиент.**

+ Минимум миграции на старте.
+ Меньше изменений в runtime.
− LLM behavior расползается по сервисам.
− Routing/prompt policy дублируется.
− Тяжело делать stateful conversation workflows.

**B. Построить один большой "умный API", который и анализирует чат, и отвечает клиентам.**

+ Один процесс, одна точка AI-интеграции.
− Смешиваются ingestion, analysis, retrieval и synthesis.
− Становится трудно изолировать side effects.
− API начинает зависеть от длинных batch/workflow задач.

**C. Ввести отдельный `ai-orchestrator`, отделить deterministic projection и embeddings, а routing вынести в отдельный policy-driven слой.**

+ Вся сложная AI-логика живёт в одном месте.
+ Persistence остаётся deterministic.
+ Можно централизованно управлять провайдерами, fallback и observability.
+ LangGraph применяется ровно там, где нужны checkpoints и branching.
− Нужен migration path от текущих сервисов.
− Появляется ещё один важный архитектурный слой, который нужно хорошо тестировать.

## Решение

**C — единый `ai-orchestrator` + `memory-projector` + `embedding-indexer` + task-based multi-LLM routing.**

### Что принимаем

1. `ai-orchestrator` становится единственной точкой сложной LLM-оркестрации.
2. LangGraph используется внутри `ai-orchestrator` для stateful workflows.
3. LLM никогда не пишет в Postgres/Neo4j/Qdrant/S3 напрямую.
4. Все extraction/summarization outputs обязаны быть structured и Pydantic-валидируемыми.
5. Routing идёт по семействам задач:
   - `extract_structured`
   - `summarize_window`
   - `synthesis`
   - `embed_text`
6. Основной routing для текста:
   - primary: Wormsoft
   - fallback: Polza
7. Embeddings идут по profile-aware схеме:
   - один active embedding profile за раз;
   - collection alias в Qdrant;
   - controlled reindex при profile switch.

## Почему не "LangChain везде"

Мы принимаем LangGraph/LangChain как полезный AI runtime слой, но не как замену всей архитектуре.

- **LangGraph** — для orchestration и state.
- **LangChain** — для structured outputs и provider abstraction.
- **Обычный Python** — для ingestion, projection, retrieval planning и maintenance.

Это соответствует принципу: deterministic workflows предпочтительнее, если они покрывают use case.

## Последствия

- (+) Архитектура становится проще для наблюдения и контроля.
- (+) Легче менять провайдера или prompt policy без переписывания нескольких сервисов.
- (+) API остаётся grounded retrieval boundary, а не ещё одним неуправляемым агентом.
- (+) Embeddings получают нормальный lifecycle и rollback strategy.
- (−) Нужно постепенно перенести логику из `entity-extractor` / `persona-builder` / `task-extractor` / `chat-summarizer`.
- (−) Нужны golden tests и shadow rollout для orchestration layer.

## Новая целевая структура сервисов

- `telegram-ingestor`
- `ai-orchestrator`
- `memory-projector`
- `embedding-indexer`
- `mcp-rest-api`
- `maintenance`
- `xray`

Текущие extractor-сервисы разрешены как переходный слой, но не как финальная форма архитектуры.
