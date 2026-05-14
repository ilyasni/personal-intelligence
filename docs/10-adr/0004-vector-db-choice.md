# ADR 0004: Qdrant как vector DB, pgvector — backup-вариант

- Дата: 2026-05-11
- Статус: Accepted

## Контекст

Нужен векторный поиск с:
- payload-фильтрацией,
- hybrid search (vector + payload),
- быстрым self-host,
- хорошим Python SDK.

## Варианты

**A. Qdrant.**
+ Простой self-host, snapshot/restore встроены.
+ Богатые payload-индексы и фильтры.
+ Hybrid (vector + payload + sparse в новых версиях).
+ Хороший Python SDK.
− Ещё один сервис в стэке.
− Память на embeddings отдельная (хотя есть `on_disk=true`).

**B. pgvector в Postgres.**
+ Не нужен отдельный сервис.
+ Транзакционная консистентность с canonical model.
− HNSW в pgvector моложе и медленнее на больших коллекциях.
− Mixed workload (OLTP + ANN) в одной БД — рискованно для p95.
− Меньше hybrid-фич.

**C. Weaviate / Milvus / Vespa.**
+ Возможности.
− Эксплуатация тяжелее.
− Сообщество в Python-проектах меньше под self-host.

**D. ElasticSearch / OpenSearch.**
+ Hybrid из коробки.
− Тяжёлый stack, JVM, требует тюнинга.

## Решение

**A — Qdrant.**

pgvector держим как «план Б» — если в MVP-3 окажется, что отдельный сервис не оправдан (низкий объём, простые запросы), мигрируем в Postgres.

## Пересмотр

Триггеры для перехода на pgvector:
- < 100К chunks с горизонтом ≤ 3 лет;
- латентность Qdrant выше латентности pgvector ANN на нашем хардваре;
- эксплуатационная нагрузка (snapshot/restore/upgrade) превышает выгоду.

Триггеры остаться на Qdrant:
- > 1М chunks;
- hybrid-запросы становятся регулярными;
- появляется потребность в multi-tenant collections.

## Последствия

- (+) Снимаем нагрузку с Postgres.
- (+) Простой path для re-embedding.
- (−) Ещё один backup-кандидат.
- (−) Доп. артефакт CI (qdrant snapshot diff в restore-drill).
