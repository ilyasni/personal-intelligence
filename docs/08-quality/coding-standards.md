# Coding standards

> Если примерная структура репозитория ниже расходится с новой AI-архитектурой, ориентируйся на [../02-architecture/ai-integrated-architecture.md](../02-architecture/ai-integrated-architecture.md) и [../02-architecture/components.md](../02-architecture/components.md).

Общие правила для всего кода в monorepo. Соблюдают все три агента (Claude Code / Codex / Cursor) одинаково.

## Структура репозитория

```
.
├── apps/                 # фронтенды
│   └── admin-ui/
├── services/             # бэкенд-сервисы
│   ├── telegram-ingestor/
│   ├── entity-extractor/
│   ├── persona-builder/
│   ├── task-extractor/
│   ├── chat-summarizer/
│   ├── memory-distiller/
│   ├── graph-builder/
│   ├── mcp-rest-api/
│   └── maintenance/
├── libs/                 # общие библиотеки
│   ├── contracts/
│   ├── llm-client/
│   ├── retrieval/
│   ├── auth/
│   ├── cache/
│   ├── observability/
│   └── storage-clients/
├── infra/
│   ├── compose/
│   ├── k8s/              # MVP-3 (опц.)
│   ├── grafana/
│   └── prometheus/
├── migrations/
│   ├── postgres/         # alembic
│   ├── neo4j/            # cypher
│   └── qdrant/           # python скрипты ensure_collections
├── scripts/
│   ├── dev/
│   └── ops/
├── tests/
│   ├── fixtures/
│   ├── load/
│   ├── e2e/
│   └── visual/
├── docs/
├── Makefile
├── pyproject.toml        # root: dev-зависимости + ruff/mypy
└── package.json          # root: shared lint конфиги
```

## Python

- Версия — 3.12.
- Менеджер зависимостей — Poetry, per-сервис `pyproject.toml`.
- Линтер — ruff (включая isort), форматтер — ruff format (alias black).
- Тайпчек — mypy (strict для libs, relaxed для services где есть LLM-ответы).
- Async везде, где IO; синхронные блокирующие функции — только в скриптах.
- Логирование — `structlog`, JSON, обязательные поля: `service`, `trace_id`, `event_id` где применимо.
- Конфигурация — `pydantic-settings`, читается из env.
- Исключения — собственные классы в `libs/contracts/errors.py`, наследники от `PILError`.
- Никаких `from x import *`.
- Public API модуля документируется docstring'ами в стиле Google.

### Naming
- модули — snake_case, классы — CapWords, функции — snake_case.
- pydantic-модели — `XxxEvent`, `XxxCommand`, `XxxModel` (для БД).

### Структура сервиса

```
services/<name>/
├── pyproject.toml
├── src/<name>/
│   ├── __init__.py
│   ├── main.py            # entrypoint, инициализация
│   ├── config.py          # pydantic-settings
│   ├── consumers/         # consumer-handlers
│   ├── handlers/          # FastAPI routes (если есть HTTP)
│   ├── domain/            # чистая логика
│   ├── infra/             # клиенты к БД/шине
│   └── observability.py
└── tests/
    ├── unit/
    └── integration/
```

## TypeScript / React

- Vite + TypeScript strict.
- Biome (или ESLint + Prettier) — выбрать в первой неделе MVP-1, зафиксировать в `.editorconfig`.
- React 18+, функциональные компоненты, hooks. Никаких классов.
- State — TanStack Query для server state, useState/useReducer для local.
- Стили — Tailwind utility-first. Tokens — в `tailwind.config.ts`.
- Файл компонента — `PascalCase.tsx`, hook — `useCamelCase.ts`, util — `kebab-case.ts`.

## Git

- Транк-based: `main` всегда зелёный.
- Feature ветки: `feat/<short-desc>`, `fix/<id>`, `refactor/<area>`.
- Conventional commits: `feat(persona): add trust_score formula`, `fix(ingestor): handle FloodWait`.
- PR ≤ 400 строк диффа (исключения — миграции и автогенерация).
- Squash-merge с осмысленным заголовком.
- Не пушим в `main` напрямую.
- Каждый PR — handoff-блок в описании (см. [../11-agents/handoff-protocol.md](../11-agents/handoff-protocol.md)).

## Контракты и контрактные тесты

- `libs/contracts` — единственный источник правды для событий и API-моделей.
- При изменении модели:
  - bump `schema_version` если breaking;
  - обновить json-schema export;
  - обновить документацию в `docs/03-data-model/event-schema.md` или `docs/04-api/`.
- Каждое изменение `libs/contracts` идёт отдельным PR.

## Логи и observability

- Никаких `print`.
- Никаких сырых текстов сообщений в логах (PII!). Только `event_id`, `chat_id`, `person_id`.
- Корреляционный `trace_id` пробрасывается из ingestion через все consumers.
- Метрики в `pil_<service>_*` namespace.

## Секреты

- Никогда не коммитим. Pre-commit hook `gitleaks`.
- Только через env / docker secrets.
- В тестах — фиктивные значения, никаких реальных API-ключей.
- `libs/observability` маскирует подозрительные строки (api_key=..., token=...) перед логированием.

## ADR

- Любое архитектурно влияющее решение — ADR в `docs/10-adr/`.
- Шаблон — ADR-0001.

## Зависимости

- Минимизация transitive deps. Перед добавлением — проверка на `dependency-check`.
- Pinned versions (через poetry.lock).
- Renovate bot (или dependabot) обновляет minor/patch автоматически с CI-гейтом.

## Безопасность кода

- SQL — только через SQLAlchemy / параметризованные запросы.
- Cypher — параметризованный, без string interpolation.
- HTML/JSX — никакого `dangerouslySetInnerHTML` без обоснования.
- Регулярки — анализировать на ReDoS (в DLQ пишутся пользовательские строки!).

## Документация в коде

- README у каждого сервиса/либы (короткий, 10 строк): purpose, entrypoint, run-команда, owner.
- Docstrings для public API.
- Жирные «почему так» — в `docs/`, не в комментариях.
