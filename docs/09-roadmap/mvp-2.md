# MVP-2: граф и семантическая память

> Этот документ описывает pre-reset roadmap.
> После архитектурного обновления 2026-05-13 источником правды по целевой форме сервиса считаются [../02-architecture/ai-integrated-architecture.md](../02-architecture/ai-integrated-architecture.md) и [milestones.md](milestones.md).

**Цель**. Включить полноценный GraphRAG: Neo4j-граф связей + Qdrant memory + LLM-улучшенный summarizer. MCP отдаёт богатый контекст.

**Длительность**: 8 недель.

## Scope

В:
- Neo4j 5 в стэк, constraints, graph-builder сервис.
- Qdrant 1.10, коллекции `memory_chunks`, `person_summaries`, `interaction_summaries`.
- `services/memory-distiller` MVP-полный (с simhash dedup и re-embed).
- LLM-summarizer (cloud opt-in / local default).
- `libs/retrieval` — композитор GraphRAG (SQL + Cypher + Qdrant).
- MCP-инструменты: `graph_walk`, `search_memory`, `recall_with_query`, `who_works_at`.
- Admin UI: Memory page, Person Graph tab (react-flow), DLQ retry UI, jobs page.
- Cascade erase каскад в Neo4j + Qdrant + object storage.
- Partitioning `interaction`, `processed_event`, `audit_log`.
- Re-embed job для смены модели embedding.
- Restore drill каждый месяц по cron.

Не в:
- Multi-account.
- Speech-to-text.
- K8s.
- Proactive notifications.

## Тикеты по слоям

### Layer A — storage
- A-01. Добавить Neo4j в compose, constraints migration. (Codex.)
- A-02. Добавить Qdrant в compose, ensure_collections. (Codex.)
- A-03. Партиционирование `interaction` (monthly) + bgworker для создания партиций на месяц вперёд. (Codex.)
- A-04. Backfill snapshots — добавить Qdrant `POST /snapshots` и Neo4j dump в maintenance. (Codex.)

### Layer B — pipelines
- B-01. `services/graph-builder` (consumer всех processing-событий → Cypher). (Codex + Claude Code для архитектуры.)
- B-02. `services/memory-distiller` — interaction → chunk, embed (bge-m3 local), upsert Qdrant. (Claude Code.)
- B-03. simhash dedup в memory-distiller. (Codex.)
- B-04. Chat summarizer: LLM-mode с structured output. (Claude Code.)
- B-05. Persona builder: LLM-style + embedding в `person_summaries`. (Claude Code.)
- B-06. Entity extractor: hybrid mode (rule + LLM на низком confidence). (Claude Code.)
- B-07. Decay job для graph weights. (Codex.)

### Layer C — retrieval & MCP
- C-01. `libs/retrieval` — `build_person_context` (Postgres + Neo4j + Qdrant). (Claude Code.)
- C-02. `libs/retrieval` — `recall_with_query` (free-form q → структурированный ответ + citations). (Claude Code.)
- C-03. MCP-инструменты: `graph_walk`, `search_memory`, `recall_with_query`, `who_works_at`. (Cursor + Claude Code.)
- C-04. Acceptance суйта retrieval: разметка 50 «good queries» с эталонными top-K, ROUGE/precision@K в CI gate. (Claude Code + Codex.)

### Layer D — admin UI
- D-01. Person card: Graph tab (react-flow 1-hop). (Cursor.)
- D-02. Memory page (search + recall). (Cursor.)
- D-03. DLQ retry UI + jobs page. (Cursor.)
- D-04. Privacy review page. (Cursor.)

### Layer E — privacy
- E-01. Cascade erase saga (Postgres + Neo4j + Qdrant + object storage). (Claude Code — сквозная задача.)
- E-02. Re-embed job (смена модели embedding без потери данных). (Codex.)
- E-03. Per-pipeline LLM mode guard (запрет cloud-call если local выбран). (Codex.)

### Layer F — quality
- F-01. Load test 50 msg/sec sustained 10 min. (Codex.)
- F-02. Visual snapshot тесты по всем экранам UI. (Cursor.)
- F-03. Restore drill автоматизирован, отчёт в audit. (Codex.)

## Acceptance criteria

- [ ] Граф 1-hop отображается в Person card, переход по узлам работает.
- [ ] `recall_with_query` через MCP возвращает ответ с citations за ≤ 2 сек P95 на seed.
- [ ] Precision@5 на размеченной выборке ≥ 0.7.
- [ ] Cascade erase удаляет данные во всех 4 хранилищах за ≤ 30 сек на типовой Person.
- [ ] Re-embed смены модели проходит без остановки сервиса.
- [ ] Restore drill зелёный.

## Риски

- Качество LLM-summary на RU — нужно валидировать на конкретной модели; cloud-mode может потребоваться для приличного качества.
- Размер Qdrant: оценочно ~5–10 GB на год активной переписки. На SSD с `on_disk=true` ОК, но мониторить.
- Cascade erase saga может частично упасть — обязательно идемпотентный retry.
