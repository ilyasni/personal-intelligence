# Knowledge Base Usage

Этот документ фиксирует роли трёх хранилищ знаний в новой AI-архитектуре PIL.

## Каноническое правило

**Postgres — единственный source of truth.**

Qdrant и Neo4j считаются derived projections, которые можно перестроить из canonical данных.

## First-party vs third-party

В canonical AI-модели нужно жёстко разделять:

- `owner_profile` / first-party identity владельца;
- `relationship_annotation` / first-party контекст владельца относительно конкретных людей и чатов;
- `person` / third-party людей, с которыми владелец общается.

Сообщения владельца не должны трактоваться как "ещё одна персона в списке контактов". Они должны использоваться как first-party context для интерпретации людей, чатов, задач и retrieval.

Текущий runtime уже хранит канонический `owner_profile`, но всё ещё использует переходную backing record в `person(is_owner=true)` для совместимости с частью pipeline и detail/read-path логики.

## Postgres

В Postgres хранятся:

- `owner_profile`
- `relationship_annotation`
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

В canonical first-party relationship layer должны жить operator-defined annotations:

- relationship labels вроде `коллега`, `супруга`, `семья`, `pet-проект`;
- relationship labels для чатов и каналов вроде `работа`, `семья`, `внутренний контур`, `клиенты`;
- owner notes about the relationship and segmentation intent.

Дополнительно в canonical person-layer могут жить более нейтральные contact-level annotations:

- manual tags / labels владельца;
- owner comments / notes;
- future segmentation hints, введённые человеком, а не моделью.

Это нужно, чтобы бизнес- и личные сегменты не зависели только от AI-интерпретации и не перегружали саму карточку контакта ролью owner-context.

Но эти поля относятся к внешним людям. Для самого владельца уже используется отдельный first-party profile layer `owner_profile`, а не self-contact в `person`.

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
- `person_manual_tags`
- `kind`
- `topic_tags`
- `ts_from`
- `ts_to`
- `embedding_profile`
- `schema_version`
- `analysis_window_id`
- `source_window_id`

`owner_id` здесь — это first-party principal, а не ordinary contact row.

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

Manual tags владельца не должны становиться отдельным источником правды в Neo4j.
Если они и проецируются в граф, то только как derived labels from Postgres canonical annotations.

First-party owner identity в конечной схеме тоже не должна жить как ordinary `Person` node. Допустима переходная проекция для совместимости, но target graph обязан различать owner context и external persons.

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
