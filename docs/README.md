# Документация PIL

Документация — **общая для всех трёх агентов** (Claude Code, Codex, Cursor) и для людей. Каждый агент при старте сессии читает соответствующую точку входа в корне репозитория ([`../CLAUDE.md`](../CLAUDE.md), [`../AGENTS.md`](../AGENTS.md), [`../.cursorrules`](../.cursorrules)), а оттуда — погружается в этот каталог.

## Где что лежит

- [00-overview](00-overview) — большая картина и глоссарий.
- [01-product](01-product) — PRD, jobs-to-be-done, privacy.
- [02-architecture](02-architecture) — система, компоненты, потоки, стек, деплой.
- [03-data-model](03-data-model) — Postgres / Neo4j / Qdrant / event schema.
- [04-api](04-api) — MCP, REST, OpenAPI.
- [05-pipelines](05-pipelines) — ingestion и шесть процессинговых сервисов.
- [06-admin-ui](06-admin-ui) — спека интерфейса и UX-флоу.
- [07-operations](07-operations) — Docker Compose, Proxmox, мониторинг, бэкапы, runbook.
- [08-quality](08-quality) — тестовая стратегия, стандарты кода, CI/CD.
- [09-roadmap](09-roadmap) — MVP-1/2/3 и milestones.
- [10-adr](10-adr) — Architecture Decision Records.
- [11-agents](11-agents) — агентская архитектура, конвенции, handoff.

## Reference-файлы автора

Исходные материалы, на которых строится проект (русский, длинные):

- [Исполнительное резюме.md](Исполнительное%20резюме.md)
- [Привязка ботов к аккаунту Telegram подробный анализ функции и практические кейсы.md](Привязка%20ботов%20к%20аккаунту%20Telegram%20подробный%20анализ%20функции%20и%20практические%20кейсы.md)

## Как читать впервые

1. [00-overview/big-picture.md](00-overview/big-picture.md) — 3 минуты.
2. [02-architecture/system-overview.md](02-architecture/system-overview.md) — 10 минут.
3. [01-product/PRD.md](01-product/PRD.md) — 10 минут.
4. [11-agents/agent-architecture.md](11-agents/agent-architecture.md) — 5 минут.
5. [09-roadmap/mvp-1.md](09-roadmap/mvp-1.md) — 10 минут.

Дальше — по необходимости.

## Соглашения

- Русский язык в прозе, английский — в идентификаторах, командах, путях.
- Mermaid-диаграммы прямо в markdown.
- Каждое архитектурное решение фиксируется как ADR ([10-adr](10-adr)).
- Любое изменение спеки идёт в том же PR, что и код.
