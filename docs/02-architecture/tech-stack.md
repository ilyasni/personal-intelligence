# Tech stack

## Версии и выборы

| Слой | Технология | Версия / статус | Почему |
|---|---|---|---|
| Язык | Python | 3.12 | async-first, богатая AI-экосистема |
| API | FastAPI | current | MCP/REST boundary, OpenAPI, async |
| Telegram | Telethon + Bot API adapter | current | нужен доступ и к userbot-паттернам, и к business flows |
| Event bus | Redis Streams | Redis 7.x | consumer groups, DLQ-паттерны, проще Kafka для single-node |
| Canonical DB | PostgreSQL | 16 | transactions, partitions, JSONB, auditable canonical state |
| Graph DB | Neo4j | 5.x | relationship-centric retrieval |
| Vector DB | Qdrant | 1.10+ | payload filters, hybrid search, self-host fit |
| Object storage | S3-compatible cloud.ru | current | raw payloads, media, interaction artifacts |
| AI orchestration | LangGraph | 1.x | durable stateful workflows, checkpoints, branching |
| LLM framework | LangChain | current | structured output, provider abstraction, tool-friendly integration |
| Schema / contracts | Pydantic | 2.x | strict structured outputs and event contracts |
| Text routing primary | Wormsoft | current | already integrated in adjacent systems, OpenAI-compatible |
| Text routing fallback | Polza | current | second OpenAI-compatible provider for structured text tasks |
| Embeddings | Wormsoft **или** Polza | profile-based | один active profile за раз, controlled migration |
| Observability | OpenTelemetry + Prometheus + Grafana | current target | traces, metrics, routing visibility |
| Scheduler | APScheduler | current | maintenance, reindex, profile switch jobs |
| Deploy | Docker Compose now, K8s optional later | current/optional | self-host on Proxmox first |

## Ключевые технологические решения

### LangGraph — только там, где он реально нужен

Используем LangGraph в `ai-orchestrator`, потому что там есть:

- state между шагами;
- checkpoint boundaries;
- retries и resumable reprocess;
- branching по confidence / content type;
- future human-in-the-loop points.

Не используем LangGraph для:

- ingestion;
- projector/writer services;
- simple API handlers;
- housekeeping.

### LangChain — как framework around models, а не как магия

Берём из LangChain то, что полезно в production:

- structured outputs;
- provider abstraction;
- prompt/tool interfaces;
- удобную интеграцию с LangGraph.

Не строим "агентов ради агентов". Deterministic workflow остаётся предпочтительным паттерном.

### Embeddings — profile-aware

Для embeddings архитектурно важно не количество провайдеров, а совместимость профиля.

Поэтому:

- активен только один embedding profile;
- Qdrant collection versioning обязателен;
- profile switch идёт через alias + controlled reindex;
- automatic fallback между несовместимыми профилями запрещён.

### Qdrant — dense first, hybrid-ready

Базовый профиль:

- dense vector на summary/window/fact text;
- payload filters по `chat_id`, `person_ids`, `kind`, `ts`, `embedding_profile`.

Целевой профиль:

- dense + sparse/BM25 hybrid retrieval для лучшего recall по чатам и коротким фразам.

## Что мы осознанно не делаем

- **Не делаем один LLM на всё.**
  Extraction, summarization, synthesis и embeddings — разные семейства задач.

- **Не пускаем LLM напрямую в базы.**
  Side effects отделены в `memory-projector`.

- **Не смешиваем много embedding profiles в одной active collection.**
  Это ломает качество retrieval и усложняет rollback.

- **Не превращаем API в автономного агента.**
  Сначала retrieval, потом synthesis.
