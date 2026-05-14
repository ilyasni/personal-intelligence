# Testing strategy

Текущее состояние на 2026-05-12:

- в репозитории есть только `tests/integration/`;
- `make test` и `make verify` запускают `pytest tests/ -v`;
- unit/UI/e2e split пока описан как целевая структура.

## Уровни

### Unit
- Целевое расположение: `services/<svc>/tests/unit/`, `libs/<lib>/tests/`.
- pytest + pytest-asyncio. Pure-function priority.
- Coverage gate и `make coverage` — следующий этап.

### Integration
- testcontainers: запускаем postgres / neo4j / qdrant / redis / minio в Docker на время теста.
- Конфиг `tests/conftest.py` дёргает `pytest-asyncio` event_loop + создаёт чистые БД.
- Длительность: целевая ≤ 5 мин на CI runner.

### E2E
- Playwright для admin-ui + бэкенда после появления UI/API-слоя.
- Сценарии — соответствуют [docs/06-admin-ui/ux-flows.md](../06-admin-ui/ux-flows.md).
- Плановый запуск: `make e2e`. CI — после появления UI и workflow A-06.

### Smoke
- Лёгкий набор (≤ 30 сек) для post-deploy.
- `make smoke` — текущий wrapper из полного checkout, который показывает healthchecks контейнеров.
- Фактическая pipeline-проверка пока делается вручную по compose health + логам после тестового сообщения.

### Contract
- `libs/contracts` имеет JSON-Schema-валидаторы для каждого события.
- Pre-commit hook: каждый pydantic-model в `libs/contracts` должен сериализовываться и десериализоваться без потерь.

### Visual regression
- Playwright snapshot ключевых экранов.
- При diff — UI-инженер ревьюит и обновляет baseline.

### Load (опционально, MVP-2)
- locust-сценарий `tests/load/ingest_stream.py` — публикация N msg/sec в Redis Stream.
- Acceptance: 50 msg/sec sustainable.

## Тестовая пирамида (цель)

```
   /\
  /  \     E2E + visual: ~30 сценариев
 /----\    Integration: ~150 сценариев
/      \   Unit: 1500+ сценариев
--------
```

## Mocks vs real

- LLM-вызовы — всегда мокаются в unit и integration. Использовать `pytest-recording` (vcrpy) для realistic responses.
- Embeddings — стабильные fixtures (`tests/fixtures/embeddings.json`). Не вызываем модель в CI.
- Telethon — мокать через `aioresponses` + кастомный stub `tests/fakes/telethon.py`.
- Cloud LLM — никогда не сетим в CI. Live-prove только в `tests/live/` (запускается локально вручную).

## CI gate

- GitHub Actions `ci.yml` обязателен зелёный для merge.
- Локально перед отправкой всё ещё ожидается `make verify`.
- Coverage upload появится в следующей итерации CI.
- `ruff`/`mypy` пока не включены в обязательный GitHub gate из-за текущего static-analysis debt; CI вернёт их после отдельной cleanup-итерации.
- Security — `pip-audit`, `safety`, `npm audit`, `trivy` для image — CI fail на high-severity без override.

## Data fixtures

Целевая структура `tests/fixtures/`:

- `persons/*.json` — представительные профили.
- `chats/*.json` — синтетические переписки RU+EN.
- `events/*.jsonl` — потоки событий.
- `embeddings.json` — стабильные эмбеддинги для seed-чанков.

Генератор `scripts/dev/gen_fixtures.py` пока запланирован тикетом B-03.

## Поведение в случае ML/LLM

LLM по природе недетерминированна, потому для тестов:

- Используем `temperature=0` и фиксируем seed где возможно.
- Snapshot тесты проверяют **структуру** ответа, не точный текст.
- Acceptance — диапазон метрики (ROUGE/Precision) с допуском.

## Anti-patterns

- Тесты, читающие реальный Telegram → не делать в CI.
- Тесты, зависящие от точного текста LLM → fragile, заменять на структурные ассерты.
- Долгие integration > 30 сек на тест → разбивать или мокать тяжёлое.

## Запуск

```bash
make test              # текущий pytest tests/ -v
make verify            # lint + typecheck + test
```
