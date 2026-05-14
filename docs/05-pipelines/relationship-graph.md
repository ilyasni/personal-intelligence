# Pipeline: Relationship Graph (graph-builder)

> Этот документ отражает pre-reset design.
> В актуальной target-архитектуре отдельный `graph-builder` не является обязательным финальным сервисом; graph projection переносится в `memory-projector`. См. [../02-architecture/ai-integrated-architecture.md](../02-architecture/ai-integrated-architecture.md).

`services/graph-builder` — пишет узлы и рёбра в Neo4j на основе событий.

## Вход

- `events.telegram.message` — для `CO_CHAT`, базовые `MEMBER_OF`.
- `events.processing.entity_found` — для `MENTIONS`, `WORKS_AT`, `DISCUSSED`.
- `events.processing.task_created` — для `OWES_TO`.
- `events.telegram.message_deleted` — корректирует weights (вычитает 1 из `count`, не ниже 0).

## Выход

- Neo4j: узлы и рёбра по [docs/03-data-model/neo4j-graph-model.md](../03-data-model/neo4j-graph-model.md).

## Алгоритм

1. Из payload события вычисляем целевую операцию (см. таблицу ниже).
2. Через `libs/storage-clients/neo4j` исполняем Cypher UPSERT.
3. Идемпотентность — через `processed_event` (consumer_name='graph-builder').

| Событие                          | Cypher (упрощённо)                              |
|----------------------------------|--------------------------------------------------|
| `telegram.message` (в групп. чате) | `MERGE (:Person {id:owner})`, `MERGE (:Chat {id:chat})`, `MERGE (owner)-[:MEMBER_OF]->(chat)` |
| `processing.entity_found` (mention)| `MERGE (s:Person {id:speaker}) MERGE (m:Person {id:mentioned}) MERGE (s)-[r:MENTIONS]->(m) ON CREATE SET r.count=1, r.weight=0.1, r.last_at=ts ON MATCH SET r.count = r.count + 1, r.weight = least(r.weight + 0.05, 1), r.last_at=ts` |
| `processing.entity_found` (org)  | `MERGE (p:Person {id:speaker})`, `MERGE (o:Organization {slug:org})`, `MERGE (p)-[w:WORKS_AT]->(o)` (только если confidence ≥ 0.8) |
| `processing.task_created`        | `MERGE (o:Person {id:owner}) MERGE (c:Person {id:counterpart}) MERGE (o)-[r:OWES_TO]->(c) ON CREATE SET r.open_count=1 ON MATCH SET r.open_count = r.open_count + 1` |
| `processing.task_resolved`       | `MATCH (o)-[r:OWES_TO]->(c) SET r.open_count = greatest(r.open_count - 1, 0)` |

## Decay job

- `services/maintenance` запускает раз в сутки:
  ```cypher
  MATCH ()-[r:MENTIONS|CO_CHAT|KNOWS]->() SET r.weight = r.weight * 0.99
  ```
- Удаление слабых рёбер (опц., чтобы граф не разбухал):
  ```cypher
  MATCH ()-[r:MENTIONS]->() WHERE r.weight < 0.01 DELETE r
  ```

## Конфигурация

```
GRAPH_NEO4J_URI=bolt://neo4j:7687
GRAPH_NEO4J_USER=neo4j
GRAPH_NEO4J_PASSWORD=...
GRAPH_MENTIONS_DELTA=0.05
GRAPH_DECAY_FACTOR=0.99
GRAPH_DECAY_FLOOR=0.01
```

## Observability

- `pil_graph_writes_total{type}`
- `pil_graph_decay_runs_total`
- `pil_graph_nodes_total`, `pil_graph_edges_total` (gauge, periodic scan)

## Тесты

- Unit — Cypher-генерация (используем cypher-builder либу или string-templates с фиксированными формами).
- Integration — testcontainers Neo4j; проверка constraints, UPSERT идемпотентности, decay-job.

## Open questions

- Q-GRP-1. Использовать ли APOC для batch-upsert при backfill? — требует апдейта Neo4j image.
- Q-GRP-2. Хранить ли историю изменений `weight` (отдельной коллекцией событий)?
