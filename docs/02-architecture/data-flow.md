# Потоки данных

Ключевые sequence-диаграммы для целевой AI-архитектуры.

## 1. Message -> Memory

```mermaid
sequenceDiagram
  participant TG as Telegram
  participant Ing as telegram-ingestor
  participant Bus as Redis Streams
  participant Orch as ai-orchestrator
  participant LLM as Wormsoft/Polza
  participant Proj as memory-projector
  participant Emb as embedding-indexer
  participant PG as Postgres
  participant Neo as Neo4j
  participant Qdr as Qdrant
  participant S3 as S3

  TG-->>Ing: new message / edit / media
  Ing->>S3: put raw payload or media (optional)
  Ing->>Bus: XADD events.telegram.message
  Bus-->>Orch: consume
  Orch->>PG: load context (persons, tasks, recent interactions)
  Orch->>LLM: structured extraction + summary
  LLM-->>Orch: facts/tasks/summary/persona updates
  Orch->>Bus: XADD projection commands
  Bus-->>Proj: consume projection commands
  Bus-->>Emb: consume embedding jobs
  Proj->>PG: upsert canonical records
  Proj->>Neo: merge relationship edges
  Proj->>S3: store interaction window artifact
  Emb->>LLM: embedding request
  LLM-->>Emb: dense vector
  Emb->>Qdr: upsert point + payload
```

## 2. Retrieval through MCP/REST

```mermaid
sequenceDiagram
  participant Client as MCP client / external LLM
  participant API as mcp-rest-api
  participant Ret as libs/retrieval
  participant PG as Postgres
  participant Neo as Neo4j
  participant Qdr as Qdrant
  participant LLM as Wormsoft/Polza
  participant Audit as audit_log

  Client->>API: get_person_context / search_memory / get_tasks
  API->>Audit: log request start
  API->>Ret: build retrieval plan
  par grounded retrieval
    Ret->>PG: fetch canonical state
    Ret->>Qdr: semantic or hybrid search with payload filters
    Ret->>Neo: graph walk if needed
  end
  Ret-->>API: grounded context bundle
  opt synthesis requested
    API->>LLM: grounded synthesis only
    LLM-->>API: concise answer with evidence references
  end
  API->>Audit: log completion
  API-->>Client: context or synthesized answer
```

## 3. Embedding profile switch

```mermaid
sequenceDiagram
  participant Owner
  participant API as admin / control plane
  participant Maint as maintenance
  participant PG as Postgres
  participant Emb as embedding-indexer
  participant Qdr as Qdrant

  Owner->>API: switch embedding profile to wormsoft-embed-v1
  API->>Maint: queue controlled reindex
  Maint->>PG: enumerate active memory records
  Maint->>Emb: enqueue reindex jobs
  Emb->>Qdr: write to profile-specific collection
  Maint->>Qdr: move alias pil_memory_active
  Maint-->>API: profile switch completed
```

## 4. Reprocess / backfill with checkpoints

```mermaid
sequenceDiagram
  participant Owner
  participant API as admin / control plane
  participant Orch as ai-orchestrator
  participant Bus as Redis Streams
  participant Store as checkpoint store

  Owner->>API: reprocess chat window
  API->>Bus: enqueue reprocess command
  Bus-->>Orch: consume reprocess command
  Orch->>Store: restore or create workflow state
  Orch->>Store: checkpoint after each node
  Orch->>Bus: emit projection commands
  Orch-->>API: status / progress
```

## Минимальные гарантии

- Каждое raw событие имеет стабильный `event_id`.
- Каждый projection command имеет собственный `command_id`.
- `memory-projector` и `embedding-indexer` идемпотентны.
- LLM output не применяется без schema validation.
- Routing decisions и provider results логируются отдельно от бизнес-сущностей.
