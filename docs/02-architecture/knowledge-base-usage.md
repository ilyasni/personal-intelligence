# Knowledge Base Usage

Этот документ фиксирует роли трёх хранилищ знаний в новой AI-архитектуре PIL.

## Каноническое правило

**Postgres — единственный source of truth.**

Qdrant и Neo4j считаются derived projections, которые можно перестроить из canonical данных.

## Postgres

В Postgres хранятся:

- `person`
- `chat`
- `chat_membership`
- `task`
- `interaction`
- `analysis_window`
- `extracted_fact`
- `analytics_signal`
- `processed_event`
- `audit_log`

Роль Postgres:

- canonical memory;
- auditability;
- deterministic read path;
- ground truth для reprocess / rollback / reindex.

## Qdrant

Qdrant используется только как semantic retrieval projection.

Что индексируется:

- summaries окон;
- bundles фактов;
- analytics narratives;
- future memory chunks после re-embedding.

Обязательный payload:

- `owner_id`
- `chat_id`
- `person_ids`
- `kind`
- `topic_tags`
- `ts_from`
- `ts_to`
- `embedding_profile`
- `schema_version`
- `analysis_window_id`
- `source_window_id`

Текущее правило профилей:

- активен один alias: `pil_memory_active`;
- в первую волну активен один embedding profile;
- alias switch делается только после probe и acceptance.

## Neo4j

Neo4j используется только для relationship graph.

Что проецируется:

- `Person`
- `Chat`
- `Topic`
- `PARTICIPATES_IN`
- `COMMUNICATED_WITH`
- `DISCUSSES`
- `MENTIONED_TOPIC`

Роль Neo4j:

- relationship-centric queries;
- recency / reciprocity / communication strength;
- explainable graph traversal поверх evidence-backed canonical памяти.

## Retrieval precedence

В `mcp-rest-api` retrieval строится в таком порядке:

1. Postgres first
2. Qdrant second
3. Neo4j when relationship-centric
4. optional grounded synthesis last

Это означает:

- сначала factual state;
- затем semantic expansion;
- затем graph relationships;
- и только потом optional synthesis.

## Почему не наоборот

PIL не должен зависеть от vector DB как от источника правды.
Если Qdrant пуст, API всё равно обязан уметь отдавать grounded ответы по Postgres.
Если Neo4j отстал, canonical facts не должны ломаться.
