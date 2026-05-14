# 10 — Architecture Decision Records

ADR — короткие решения, фиксирующие архитектурный выбор и его последствия. Шаблон и процесс — [0001-record-architecture-decisions.md](0001-record-architecture-decisions.md).

Принятые:

- [0001](0001-record-architecture-decisions.md) — Используем ADR.
- [0002](0002-telethon-vs-business-bot.md) — Telethon + Business Bot гибрид.
- [0003](0003-event-bus-choice.md) — Redis Streams для MVP-1/2.
- [0004](0004-vector-db-choice.md) — Qdrant, pgvector как план Б.
- [0005](0005-mcp-vs-rest.md) — MCP + REST-фасад.
- [0006](0006-services-vs-monolith.md) — Monorepo с автономными сервисами.
- [0007](0007-ai-orchestration-and-multi-llm-routing.md) — Единый AI-orchestrator, LangGraph и task-based multi-LLM routing.

Открытые вопросы для будущих ADR — в [../09-roadmap/milestones.md](../09-roadmap/milestones.md) (секция «Открытые вопросы»).
