# ADR 0003: Redis Streams как event bus для MVP-1/2

- Дата: 2026-05-11
- Статус: Accepted

## Контекст

Нужен event bus с:
- consumer groups,
- персистентностью (хотя бы краткосрочной),
- DLQ-механикой,
- лёгкой эксплуатацией на одной VM.

## Варианты

**A. Redis Streams.**
+ Уже в стеке (используется как кеш и backing для ratelimit).
+ Consumer groups, XPENDING, XCLAIM — нативно.
+ Малая операционная нагрузка.
− Persist'ит ограниченно (`MAXLEN` или `MINID` policy).
− Нет встроенного DLQ — реализуем сами как `<stream>:dlq`.
− Один Redis = SPOF на MVP-1, но для одного пользователя приемлемо.

**B. Kafka.**
+ Industry-standard, мощный.
− Тяжёлая эксплуатация (Zookeeper или KRaft, тюнинг).
− Дороже по памяти/диску.
− Overkill для самого pol-нагрузки одного пользователя.

**C. NATS JetStream.**
+ Современный, лёгкий, нативные DLQ и backpressure.
+ Хорошо масштабируется.
− Меньше распространён в Python-экосистеме, чем Redis.
− Ещё один сервис к эксплуатации.

**D. Postgres LISTEN/NOTIFY + outbox.**
+ Один меньший компонент.
− NOTIFY не persist'ит, нужна outbox-таблица + воркеры — сложнее.
− Хуже throughput.

## Решение

**A — Redis Streams.** На MVP-1/2 он закрывает все потребности.

DLQ реализуем сами: на каждый поток `<stream>:dlq` для исчерпавших ретраи событий. Runbook — `docs/07-operations/runbook.md`.

Идемпотентность — на консьюмере через таблицу `processed_event` (см. event-schema).

## Пересмотр

В MVP-3 — рассмотреть переезд на NATS JetStream при:
- появлении мульти-аккаунтов (>3 tenant),
- стабильном >100 msg/sec,
- необходимости work-stealing across nodes.

## Последствия

- (+) Минимум операционной сложности.
- (+) Один Redis закрывает три потребности (bus, cache, ratelimit) — но в разных logical DB.
- (−) Стоп-слово для горизонтального масштабирования на MVP-3.
- (−) DLQ-механику пишем сами.
