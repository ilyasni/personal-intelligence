# Общие конвенции

Один набор правил для всех агентов. Если что-то нарушено — это баг, независимо от того, какой агент это сделал.

## 1. Event-first

- Все сервисы processing-слоя — consumers Redis Streams.
- Никаких прямых RPC между extractor'ами.
- Если двум сервисам нужно «общаться» — они общаются через события или через хранилище (Postgres).

## 2. Контракты в коде

- Все события и команды описаны в `libs/contracts/` как pydantic-модели.
- Любое изменение поля = bump `schema_version` (если breaking).
- Каждая модель имеет тест: `to_dict → from_dict` roundtrip.

## 3. Идемпотентность

- Каждое событие имеет уникальный `event_id` (ULID).
- Consumer перед обработкой проверяет `processed_event` (Postgres).
- Все операции записи в хранилища идемпотентны (UPSERT / MERGE / `delete by filter` без последствий повторного).

## 4. Структурные логи

- `structlog`, JSON.
- Обязательные поля: `level`, `ts`, `service`, `trace_id`, `event_id` (если есть).
- Никакого PII в логах (текст сообщений, имена, телефоны). Только IDs.

## 5. LLM-вызовы — через `libs/llm-client`

- Никаких прямых `openai.*` / `anthropic.*` в сервисах.
- `libs/llm-client` проверяет режим (`local|cloud|hybrid`) per pipeline и физически блокирует cloud-вызов, если он не разрешён.
- Метрики (tokens, latency, cost) — встроены.

## 6. Privacy by default

- Сырые сообщения не уходят в облако без явного opt-in.
- Локальный режим должен полноценно работать без интернета.
- На любое сохранение сырого текста — проверка retention policy.

## 7. ADR на развилке

- Любое архитектурно влияющее решение фиксируется ADR-stub'ом в `docs/10-adr/` ДО реализации.
- Тегаем Owner-а через комментарий в issue/PR.
- См. [ADR-0001](../10-adr/0001-record-architecture-decisions.md).

## 8. Тесты

- Любой новый код имеет тест.
- `make verify` зелёный — обязательное условие для merge.
- Регрессии — тест добавляется перед фиксом.

## 9. PR

- Предпочтительный workflow: атомарные PR, ≤ 400 строк диффа (миграции и автоген — исключения с пометкой).
- Если работа идёт в git-checkout: squash-merge, conventional commits, handoff в описании PR, ссылка на тикет в `milestones.md`.
- Если работа идёт в текущем server runtime без `.git`: обязательны handoff-файл или handoff-комментарий + обновление `milestones.md`.

## 10. Секреты

- Никогда не коммитим.
- gitleaks в pre-commit.
- Тесты используют фиктивные значения.

## 11. Документация

- Обновляется в том же PR, что и код.
- Если API/контракт изменился — обновить `docs/04-api/` и/или `docs/03-data-model/`.
- Если архитектура изменилась — обновить `docs/02-architecture/` и открыть ADR.

## 12. Эксплуатация — не «потом»

- Каждый новый сервис имеет:
  - `/healthz`,
  - `/metrics`,
  - structured logs,
  - Dockerfile минимального размера,
  - entry в compose,
  - tests/integration/.

## 13. Imports и зависимости

- Сейчас проект использует `pyproject.toml` + editable installs через `pip install -e ...`.
- Poetry/uv workspace может появиться позже, но пока не является обязательным.
- Версии pinned.

## 14. Naming

- Сервисы: `kebab-case` директории, `snake_case` Python-модули.
- Тесты: `test_<unit_under_test>.py` + класс `TestXxx`.
- Pydantic-модели: суффиксы `Event` / `Command` / `Model` / `Spec`.
- События Redis Streams: `events.<area>.<verb>` (см. event-schema).

## 15. Стиль кода

- Python: ruff (вкл. isort) + ruff format + mypy.
- TS: biome (или eslint+prettier — выбрать в неделе 1).
- См. [coding-standards.md](../08-quality/coding-standards.md).

## 16. Файловые операции

- Никогда не редактируем файлы, упомянутые в `tests/fixtures/golden/` без обновления соответствующих snapshot-тестов.
- При создании файлов — придерживаемся структуры `docs/08-quality/coding-standards.md#структура-репозитория`.

## 17. Backward compatibility

- API: одна major version в проде. Breaking — `/v2/`.
- Событий: новые поля можно добавлять без bump'а; удалять/менять тип — с bump'ом + миграцией для старых событий в DLQ.
- БД: миграции append-only. Rollback допустим только в dev.

## 18. Когда сомневаешься

1. Найди ADR в `docs/10-adr/` — может, решение уже принято.
2. Спрашивай в комментарии PR с тегом Owner-а.
3. Открывай stub-ADR с `Proposed`.

## 19. Не делать в одиночку

Эти изменения **всегда** требуют ADR + ревью Owner-а:

- новая БД / хранилище;
- удаление поля контракта событий;
- смена embedding-модели;
- смена политики приватности;
- удаление/перенос сервиса;
- новая crypto-зависимость.

## 20. Handoff

Любое завершение сессии — заполнить handoff-блок ([handoff-protocol.md](handoff-protocol.md)). Это распространяется на всех агентов и Owner-а, вне зависимости от того, был ли PR, WIP-коммит или server-side ручной прогон.
