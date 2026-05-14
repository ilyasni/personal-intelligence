# AGENTS.md — точка входа для Codex

> Документация у всех трёх агентов (Claude Code, Codex, Cursor) **общая** и лежит в `docs/`. Этот файл — твой автозагрузчик контекста при старте сессии в Codex CLI / Codex cloud.
> Зеркальные точки входа: [`CLAUDE.md`](CLAUDE.md) (Claude Code), [`.cursorrules`](.cursorrules) (Cursor).

## Миссия проекта (one-pager)

Personal Intelligence Layer (PIL) — личный второй мозг над Telegram. Бот, привязанный к профилю через Chat Automation или Telethon userbot, превращает поток сообщений в структурированную память (персоны, связи, задачи, темы, обещания) и отдаёт её внешним LLM через MCP/REST. Self-host, privacy by default.

Контекст:

- [docs/00-overview/big-picture.md](docs/00-overview/big-picture.md)
- [docs/02-architecture/system-overview.md](docs/02-architecture/system-overview.md)

## Что особенно про Codex

Codex силён в:

- **длинных автономных задачах** — массовая правка по репо, генерация большого количества тестов, написание миграций;
- **batch-режимах** — «прогони над всеми сервисами этот рефакторинг и открой PR'ы»;
- **CI-подобной работе** — починить флакающий тест, поправить lint по всему репо, обновить зависимости;
- **изолированных задачах с чёткими критериями** — есть spec, есть тест, есть acceptance criteria.

Слабее всего в: задачах, требующих частого диалога с пользователем (это к Cursor) или сквозного архитектурного планирования (это к Claude Code).

## Актуальный контекст среды

- Документация и roadmap живут в этой копии репозитория.
- Фактический runtime разворачивается на сервере `ilyasni@192.168.31.165` в директории `~/pil`.
- На сервере сейчас одна VM `personal-intelligence`; схема `pil-dev + pil-data` остаётся целевой.
- В server-side working tree сейчас нет `.git`, `docs/` и корневого `Makefile`, поэтому git/PR-процессы и `make`-обёртки из документации нужно трактовать как preferred workflow для полного checkout, а не как гарантированно доступные команды на сервере.

## Стартовые шаги новой сессии

1. Прочитать AGENTS.md.
2. Прочитать [docs/11-agents/agent-architecture.md](docs/11-agents/agent-architecture.md).
3. Прочитать [docs/11-agents/shared-conventions.md](docs/11-agents/shared-conventions.md).
4. Прочитать [docs/11-agents/handoff-protocol.md](docs/11-agents/handoff-protocol.md) — обязательно, потому что Codex чаще всего работает над тикетами, переданными от Claude Code/Cursor.
5. Сверить статус: [docs/09-roadmap/milestones.md](docs/09-roadmap/milestones.md).
6. Перед PR, merge или handoff — `make verify` в полном checkout. Если работаешь только в server runtime, явно зафиксируй, что именно проверял вручную.

## Конвенции (минимум)

Полный список — [docs/11-agents/shared-conventions.md](docs/11-agents/shared-conventions.md). Самое важное для тебя как batch-агента:

1. **Никаких массовых правок без spec.** Если задача звучит как «обнови X везде» — открой `docs/10-adr/` или зафиксируй в PR-описании rationale.
2. **PR — атомарные.** Если задача распадается на N независимых правок — N PR'ов.
3. **Тесты обязательны.** Любая логика, попадающая в PR, должна иметь тест. Codex обычно умеет генерить тесты — этим не злоупотребляй, но и не пропускай.
4. **Миграции — append-only.** Никаких правок прошедших миграций. Только новые.
5. **Контракты событий не меняем кулуарно.** Любое изменение `libs/contracts/` — отдельный PR, отдельный ADR, апдейт документации.
6. **CI всегда зелёный.** Если CI красный на main — это твой первый тикет, прежде чем браться за фичи.

## Куда смотреть по типу задачи

| Тип задачи | Сначала прочитать |
|---|---|
| Миграция Postgres | [docs/03-data-model/postgres-schema.md](docs/03-data-model/postgres-schema.md) |
| Cypher / Neo4j-схема | [docs/03-data-model/neo4j-graph-model.md](docs/03-data-model/neo4j-graph-model.md) |
| Qdrant коллекции/индексы | [docs/03-data-model/qdrant-collections.md](docs/03-data-model/qdrant-collections.md) |
| Новый pipeline / extractor | [docs/05-pipelines/](docs/05-pipelines/) |
| Тесты / qa | [docs/08-quality/testing-strategy.md](docs/08-quality/testing-strategy.md) |
| CI / релиз / Docker | [docs/08-quality/ci-cd.md](docs/08-quality/ci-cd.md), [docs/07-operations/docker-compose.md](docs/07-operations/docker-compose.md) |
| Backup / retention | [docs/07-operations/backups-and-retention.md](docs/07-operations/backups-and-retention.md) |

## Часто используемые команды

```bash
# Полный verify
make verify

# Проверить compose-стек
make ps
make logs
make smoke

# Установка зависимостей
make install
make install-dev

# Миграции и статус схемы
make migrate
make migrate-status

# Качество
make lint
make fmt
make typecheck
make test
make verify
```

## Завершение сессии (важно для Codex)

Codex чаще остальных работает «в фоне», поэтому handoff обязателен даже для WIP-сессии. Минимум:

- что сделано (с точностью до файла);
- что НЕ сделано и почему;
- какие предположения сделаны;
- какие известные риски остались;
- какой следующий шаг рекомендуется;
- какой контекст нужен следующему агенту;
- рекомендованный следующий агент: Claude Code (если нужно архитектурное продолжение), Cursor (если осталась интерактивная доводка UI), Codex (если можно продолжать в batch).

Шаблон — [docs/11-agents/handoff-protocol.md](docs/11-agents/handoff-protocol.md).
