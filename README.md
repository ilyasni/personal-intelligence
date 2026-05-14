# Personal Intelligence Layer (PIL)

Личный «интеллектуальный слой» над Telegram. Привязанный к профилю бот (через Chat Automation или Telethon userbot) наблюдает за разрешёнными чатами, извлекает из них людей, связи, задачи, темы, обещания и контекст, и предоставляет эту память внешним LLM через MCP/REST API.

> Документация **единая для всех агентов** разработки — Claude Code, Codex, Cursor. Любой агент в любой момент может подхватить любую задачу. Где это важно, в доках помечены секции «agent notes»: что особенно стоит учесть конкретному агенту (например, Codex лучше для длинных batch-задач, Cursor — для интерактивной правки UI, Claude Code — для сквозного планирования и больших рефакторов).

## Карта документации

| Раздел | Что внутри |
|--------|-----------|
| [docs/00-overview](docs/00-overview)        | Глоссарий, big picture, термины |
| [docs/01-product](docs/01-product)          | PRD, jobs-to-be-done, privacy/compliance |
| [docs/02-architecture](docs/02-architecture)| C4-диаграммы, компоненты, потоки, стек, деплой на Proxmox |
| [docs/03-data-model](docs/03-data-model)    | Postgres / Neo4j / Qdrant / event schema |
| [docs/04-api](docs/04-api)                  | MCP API, REST API, OpenAPI |
| [docs/05-pipelines](docs/05-pipelines)      | Ingestion, extractors, summarizer, graph, memory |
| [docs/06-admin-ui](docs/06-admin-ui)        | UI-spec и UX-флоу |
| [docs/07-operations](docs/07-operations)    | Docker Compose, Proxmox, мониторинг, бэкапы, runbook |
| [docs/08-quality](docs/08-quality)          | Тестовая стратегия, стандарты кода, CI/CD |
| [docs/09-roadmap](docs/09-roadmap)          | MVP-1 / MVP-2 / MVP-3, milestones |
| [docs/10-adr](docs/10-adr)                  | Architecture Decision Records |
| [docs/11-agents](docs/11-agents)            | **Агентская архитектура**: как работают Claude Code / Codex / Cursor, когда что выбирать, как передавать работу между сессиями |

Reference-материалы автора, на которых построен проект:

- [docs/Исполнительное резюме.md](docs/Исполнительное%20резюме.md)
- [docs/Привязка ботов к аккаунту Telegram подробный анализ функции и практические кейсы.md](docs/Привязка%20ботов%20к%20аккаунту%20Telegram%20подробный%20анализ%20функции%20и%20практические%20кейсы.md)

## Агентская модель разработки

Проект ведётся **одним человеком + тремя agentic-инструментами**, между которыми ты свободно переключаешься:

| Агент       | Сильная сторона                                                              | Точка входа                          |
|-------------|------------------------------------------------------------------------------|--------------------------------------|
| Claude Code | сквозной план, рефакторы по нескольким сервисам, читает много контекста      | [`CLAUDE.md`](CLAUDE.md)             |
| Codex       | длинные автономные batch-задачи (миграции, генерация тестов, массовые правки)| [`AGENTS.md`](AGENTS.md)             |
| Cursor      | интерактивная правка в редакторе, парная работа над UI, быстрые точечные изменения | [`.cursorrules`](.cursorrules) |

Все три читают одни и те же доки в `docs/` и одни и те же тикеты. Различия только в стиле инвокации и в том, какая точка входа подсасывается автоматически.

Подробнее:

- [docs/11-agents/agent-architecture.md](docs/11-agents/agent-architecture.md) — как устроен каждый агент, какие у него tool-capabilities, как он видит репо.
- [docs/11-agents/when-to-use-which.md](docs/11-agents/when-to-use-which.md) — рекомендации по выбору агента под тип задачи.
- [docs/11-agents/handoff-protocol.md](docs/11-agents/handoff-protocol.md) — как закрыть сессию у одного агента и подхватить у другого без потери контекста.
- [docs/11-agents/session-transitions.md](docs/11-agents/session-transitions.md) — что писать в commit/PR/таск, чтобы следующий агент сразу включился.
- [docs/11-agents/shared-conventions.md](docs/11-agents/shared-conventions.md) — общие правила, которым следуют все три (структурные логи, контракты, секреты, ADR).
- [docs/11-agents/prompt-library.md](docs/11-agents/prompt-library.md) — проверенные промпт-шаблоны под типовые задачи (новый сервис, миграция, рефакторинг, написать тесты, диагностика инцидента).

## Текущее состояние

На 2026-05-14 проект развивается в двух связанных средах:

- эта копия репозитория — источник документации, roadmap и рабочих инструкций для агентов;
- сервер `ilyasni@192.168.31.165`, рабочая директория `~/pil` — фактический runtime, где поднимается стек и крутятся сервисы.

Текущий server-side runtime:

- одна VM `personal-intelligence`, а не разделение на `pil-dev` и `pil-data`;
- в `~/pil` развёрнут canonical runtime: `postgres`, `redis`, `neo4j`, `qdrant`, `xray`, `telegram-ingestor`, `ai-orchestrator`, `memory-projector`, `embedding-indexer`, `mcp-rest-api`, `maintenance`;
- transitional сервисы `entity-extractor`, `persona-builder`, `task-extractor`, `chat-summarizer` сохранены в репозитории как migration history, но не являются активной server-side топологией;
- `docs/` и `scripts/` синхронизируются на сервер вместе с runtime-деревом, но `~/pil` всё ещё не является полноценным git checkout и может отставать от локального planning-repo по истории коммитов;
- `admin-ui`, observability stack и расширенный CI flow всё ещё остаются следующим этапом.

Когда в документации встречается более широкий workflow, считай его **целевым состоянием**, если рядом не сказано, что он уже реализован.

## Быстрый старт

1. Прочитать [docs/00-overview/glossary.md](docs/00-overview/glossary.md) и [docs/02-architecture/system-overview.md](docs/02-architecture/system-overview.md).
2. Сверить актуальный runtime и серверный путь: [docs/07-operations/proxmox-setup.md](docs/07-operations/proxmox-setup.md).
3. Поднять или проверить текущий compose-стек: [docs/07-operations/docker-compose.md](docs/07-operations/docker-compose.md).
4. Привязать бота и прогнать ingestion: [docs/05-pipelines/ingestion.md](docs/05-pipelines/ingestion.md).
5. Начать с активных задач из [docs/09-roadmap/milestones.md](docs/09-roadmap/milestones.md) и [docs/09-roadmap/mvp-1.md](docs/09-roadmap/mvp-1.md).

## Технологический стек (кратко)

Python 3.12/3.13, FastAPI, Telethon ≥ 1.36, Redis Streams, Postgres 16, Neo4j 5, Qdrant 1.18, S3 cloud.ru для raw storage. UI — React + Vite + Tailwind в плане MVP-1 E-layer. Контейнеризация — Docker Compose (MVP-1/2) → Kubernetes (опц. в MVP-3). Хостинг — домашний Proxmox.

Полный стек и обоснование — [docs/02-architecture/tech-stack.md](docs/02-architecture/tech-stack.md).

## Приватность

Self-host, opt-in на каждую категорию данных, минимизация сырого текста, поддержка локальных LLM (vLLM/Ollama) для полной автономии. Подробнее — [docs/01-product/privacy-and-compliance.md](docs/01-product/privacy-and-compliance.md).
