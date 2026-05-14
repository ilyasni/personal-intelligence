# CLAUDE.md — точка входа для Claude Code

> Claude Code, Codex, Cursor работают с **одной общей документацией** в `docs/`. Этот файл — твой автозагрузчик контекста: что прочитать, какие конвенции, как себя вести.
> Зеркальные файлы для других агентов: [`AGENTS.md`](AGENTS.md) (Codex), [`.cursorrules`](.cursorrules) (Cursor).

## Миссия проекта (one-pager)

Personal Intelligence Layer (PIL) — личный второй мозг над Telegram. Бот, привязанный к профилю через Chat Automation или Telethon userbot, наблюдает за разрешёнными чатами и превращает их в структурированную память: персоны, связи, задачи, темы, обещания. Память отдаётся внешним LLM через MCP/REST. Self-host, privacy by default, локальные LLM как опция.

Полный контекст:

- [docs/00-overview/big-picture.md](docs/00-overview/big-picture.md)
- [docs/02-architecture/system-overview.md](docs/02-architecture/system-overview.md)

## Что особенно про Claude Code

Claude Code хорош в:

- **сквозном планировании** — задачи на нескольких сервисах (например, «добавить новое поле во весь pipeline: event → extractor → schema → API»);
- **больших рефакторах** — переименование, разделение модуля, миграция между либами;
- **чтении большого контекста** — расследование «почему здесь так» по нескольким репо/файлам;
- **парном проектировании** — обсудить ADR, набросать архитектуру, разложить тикет.

Слабее всего в: длинных автоматических batch-прогонах (это к Codex) и в моментальной правке UI с превью (это к Cursor).

## Актуальный контекст среды

- Документация и roadmap ведутся в этой копии репозитория.
- Фактический runtime живёт на сервере `ilyasni@192.168.31.165` в `~/pil`.
- На сервере сейчас одна VM `personal-intelligence`; двух-VM топология остаётся целевой.
- В `~/pil` сейчас нет `.git`, `docs/` и корневого `Makefile`, поэтому PR/commit workflow и часть команд из документации описывают preferred-state для полного checkout, а не обязательный минимум на сервере.

## Стартовые шаги новой сессии

1. Прочитать этот файл целиком.
2. Прочитать [docs/11-agents/agent-architecture.md](docs/11-agents/agent-architecture.md) — общий контракт для агентов.
3. Прочитать [docs/11-agents/shared-conventions.md](docs/11-agents/shared-conventions.md) — стиль логов, контракты событий, секреты, ADR.
4. Прочитать [docs/11-agents/handoff-protocol.md](docs/11-agents/handoff-protocol.md) — как принять работу от предыдущей сессии.
5. Сверить статус по [docs/09-roadmap/milestones.md](docs/09-roadmap/milestones.md) и взять следующий unassigned ticket.
6. Перед первым коммитом, merge или handoff — `make verify` (lint + type + tests) в полном checkout. Если работаешь только в server runtime, явно зафиксируй ручные проверки и ограничения.

## Конвенции (минимум)

Полный список — [docs/11-agents/shared-conventions.md](docs/11-agents/shared-conventions.md). Самое важное:

1. **Event-first.** Все процессинговые сервисы — consumers Redis Streams. Никаких прямых RPC между extractor'ами.
2. **Контракты в коде.** Все события и команды — pydantic-модели в `libs/contracts/`. Меняешь поле → бампи `schema_version`, пиши миграцию для старых событий в DLQ.
3. **Идемпотентность.** Каждое событие = `event_id` (ULID). Перед записью — проверка уже-обработанного.
4. **Структурные логи.** `structlog`, JSON, `trace_id` пробрасывается из ingestion-события через весь pipeline.
5. **LLM-вызовы — через `libs/llm-client`.** Никаких прямых `openai.*` / `anthropic.*` в сервисах.
6. **Privacy by default.** Сырые тексты не уходят в облако без opt-in. Локальный режим должен полноценно работать без интернета.
7. **ADR на развилке.** Если решение влияет на архитектуру / контракты — открой stub в `docs/10-adr/` ДО реализации, тегай пользователя на ревью.

## Куда смотреть по типу задачи

| Тип задачи | Сначала прочитать |
|---|---|
| Новый extractor / pipeline | [docs/05-pipelines/](docs/05-pipelines/) + [docs/03-data-model/event-schema.md](docs/03-data-model/event-schema.md) |
| Изменение схемы Postgres | [docs/03-data-model/postgres-schema.md](docs/03-data-model/postgres-schema.md) |
| Изменение Neo4j / Qdrant | [docs/03-data-model/neo4j-graph-model.md](docs/03-data-model/neo4j-graph-model.md), [docs/03-data-model/qdrant-collections.md](docs/03-data-model/qdrant-collections.md) |
| Новый MCP/REST endpoint | [docs/04-api/](docs/04-api/) |
| Изменения Admin UI | [docs/06-admin-ui/](docs/06-admin-ui/) |
| Деплой / Proxmox / monitoring | [docs/07-operations/](docs/07-operations/) |
| Тесты / CI | [docs/08-quality/](docs/08-quality/) |

## Часто используемые команды

```bash
# Поднять только зависимости
make deps

# Поднять текущий compose-стек
make up

# Проверить состояние
make ps
make logs
make smoke

# Линт + типы + тесты
make verify

# Применить миграции
make migrate

# Уточнить статус схемы
make migrate-status
```

Все цели описаны в `Makefile` и в [docs/08-quality/coding-standards.md](docs/08-quality/coding-standards.md).

## Завершение сессии

Перед тем как «закрыть смену», заполни handoff-блок в PR/таске по форме из [docs/11-agents/handoff-protocol.md](docs/11-agents/handoff-protocol.md): что сделано, что не доделано, известные риски, рекомендованный следующий шаг и какой агент его лучше выполнит (Claude Code / Codex / Cursor). Это позволяет переключаться между агентами без потери контекста.
