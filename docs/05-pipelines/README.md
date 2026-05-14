# 05 — Pipelines

> Внимание: часть pipeline-документов ниже описывает до-reset структуру с `memory-distiller` и `graph-builder`.
> Финальная target-модель теперь зафиксирована в [../02-architecture/ai-integrated-architecture.md](../02-architecture/ai-integrated-architecture.md).

Каждый сервис ingestion/processing описан отдельно.

- [ingestion.md](ingestion.md) — Telethon + Business Bot.
- [entity-extraction.md](entity-extraction.md) — NER + topics.
- [persona-builder.md](persona-builder.md) — профиль контакта.
- [task-extractor.md](task-extractor.md) — обещания / TODO.
- [chat-summarizer.md](chat-summarizer.md) — Interaction.
- [relationship-graph.md](relationship-graph.md) — graph-builder (Neo4j).
- [memory-distiller.md](memory-distiller.md) — Qdrant memory chunks.

Контракт событий, на котором держатся пайплайны — [../03-data-model/event-schema.md](../03-data-model/event-schema.md).
