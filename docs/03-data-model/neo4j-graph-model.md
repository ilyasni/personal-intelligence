# Neo4j graph model

> Документ частично описывает pre-reset схему.
> В новой архитектуре graph projection считается производной задачей `memory-projector`, а не обязательным отдельным сервисом; см. [../02-architecture/ai-integrated-architecture.md](../02-architecture/ai-integrated-architecture.md).

Neo4j хранит **граф связей** — производный от событий и Postgres. Граф восстанавливается из событий (replay) при необходимости.

## Узлы

| Лейбл           | Ключевое свойство  | Описание                              |
|-----------------|---------------------|---------------------------------------|
| `:Person`       | `id` (UUID)         | синхронизирован с `person.id` в Postgres |
| `:Organization` | `slug`              | компании, упомянутые/выведенные       |
| `:Chat`         | `id` (UUID)         | синхронизирован с `chat.id`           |
| `:Topic`        | `slug`              | тематика (нормализованная)            |
| `:Place`        | `slug`              | локации (опц., MVP-2+)                |
| `:Project`      | `slug`              | пользовательские проекты (опц.)       |

Доп. свойства узлов — минимальные (для быстрой выборки): `display_name`, `last_seen_at`. Полные атрибуты тянем из Postgres.

## Рёбра

| Тип                            | От → к                          | Свойства                                            |
|--------------------------------|----------------------------------|-----------------------------------------------------|
| `(:Person)-[:MENTIONS]->(:Person)` | speaker → mentioned          | `weight FLOAT`, `last_at`, `count`                  |
| `(:Person)-[:KNOWS]->(:Person)`    | обоюдная                     | `strength`, `derived_from` (массив reasons)         |
| `(:Person)-[:WORKS_WITH]->(:Person)`|                              | `strength`, `since`                                 |
| `(:Person)-[:WORKS_AT]->(:Organization)`|                          | `role`, `since`, `confirmed_at`                     |
| `(:Person)-[:MEMBER_OF]->(:Chat)`  |                              | `since`, `role`                                     |
| `(:Person)-[:DISCUSSED]->(:Topic)` |                              | `count`, `last_at`                                  |
| `(:Chat)-[:ABOUT]->(:Topic)`       |                              | `weight`                                            |
| `(:Person)-[:CO_CHAT]->(:Person)`  | две person в общем чате       | `shared_chats INT`, `weight`                        |
| `(:Person)-[:OWES_TO]->(:Person)`  | task с counterpart            | `open_count`, `last_due_at`                         |

## Constraints и индексы

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
  FOR (p:Person) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT chat_id_unique IF NOT EXISTS
  FOR (c:Chat) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT organization_slug_unique IF NOT EXISTS
  FOR (o:Organization) REQUIRE o.slug IS UNIQUE;
CREATE CONSTRAINT topic_slug_unique IF NOT EXISTS
  FOR (t:Topic) REQUIRE t.slug IS UNIQUE;
CREATE INDEX person_last_seen IF NOT EXISTS FOR (p:Person) ON (p.last_seen_at);
CREATE INDEX mentions_last_at IF NOT EXISTS FOR ()-[m:MENTIONS]-() ON (m.last_at);
```

Эти constraints — обязательная часть `migrations/neo4j/001_constraints.cypher`.

## Идемпотентные upsert'ы

`graph-builder` всегда использует MERGE. Пример апдейта на MENTIONS:

```cypher
MERGE (s:Person {id: $speakerId})
  ON CREATE SET s.display_name = $speakerName, s.last_seen_at = $ts
  ON MATCH SET s.last_seen_at = $ts
MERGE (m:Person {id: $mentionedId})
  ON CREATE SET m.display_name = $mentionedName
MERGE (s)-[r:MENTIONS]->(m)
  ON CREATE SET r.count = 1, r.weight = 0.1, r.last_at = $ts
  ON MATCH SET
    r.count = r.count + 1,
    r.last_at = $ts,
    r.weight = CASE
      WHEN r.weight + 0.05 > 1 THEN 1
      ELSE r.weight + 0.05
    END
```

## Веса и распад

- Веса `MENTIONS`, `KNOWS`, `CO_CHAT` распадаются: `services/maintenance` раз в сутки умножает на `0.99` (полу-период ~70 дней).
- Реализация через периодический Cypher:
```cypher
MATCH ()-[r:MENTIONS]->() SET r.weight = r.weight * 0.99
```

## Типичные запросы

«Кто из контактов работает в Газпроме»:
```cypher
MATCH (p:Person)-[w:WORKS_AT]->(o:Organization {slug:'gazprom'})
RETURN p.id, p.display_name, w.role, w.since
ORDER BY w.since DESC
LIMIT 25;
```

Граф-walk «персона X, её 1-hop соседи и общие чаты»:
```cypher
MATCH (p:Person {id:$id})-[:CO_CHAT|MENTIONS|KNOWS*1]-(n:Person)
WITH p, collect(DISTINCT n) AS neighbors
OPTIONAL MATCH (p)-[:MEMBER_OF]->(c:Chat)<-[:MEMBER_OF]-(n2)
RETURN p, neighbors, collect(DISTINCT c) AS chats;
```

«Связать двух людей кратчайшим путём (≤3 хопа)»:
```cypher
MATCH path = shortestPath((a:Person {id:$a})-[*..3]-(b:Person {id:$b}))
RETURN path;
```

## Восстановление из событий

`scripts/ops/rebuild_graph.py`:

1. Очистить базу (`MATCH (n) DETACH DELETE n`).
2. Применить constraints.
3. Прокрутить ивенты из `events.processing.*` (Redis Stream + DLQ + архив).
4. Прогнать decay-job до текущей даты.

Время — порядка 10 минут на 1М ивентов.

## Что НЕ хранить в Neo4j

- Сами тексты сообщений и summaries — это Postgres/Object store.
- Embeddings — это Qdrant.
- Audit log — это Postgres.

## Открытые вопросы

- Q-NEO-1. Использовать ли GDS-плагин для community detection (например, найти «социальные кластеры» в графе)? Влияет на лицензию.
- Q-NEO-2. Делать ли отдельный `:Conversation` узел (диалоговый эпизод) вместо `interaction` только в Postgres? — рассмотреть в MVP-2.
