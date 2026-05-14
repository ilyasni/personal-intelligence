# Docker Compose

Базовый runtime сейчас запускается одним `docker compose -f infra/compose/docker-compose.yml up -d`.

## Актуальное состояние

- Compose-файл один: `infra/compose/docker-compose.yml`.
- `docker-compose.override.yml` сейчас не используется.
- Raw storage идёт в S3 cloud.ru, а не в локальный MinIO.
- В текущем compose уже есть `xray`, `telegram-ingestor`, `ai-orchestrator`, `memory-projector`, `embedding-indexer`, `mcp-rest-api`, `maintenance`.
- Transitional сервисы `entity-extractor`, `persona-builder`, `task-extractor`, `chat-summarizer` больше не входят в активный compose runtime.
- `admin-ui`, `prometheus`, `grafana`, `loki`, `promtail` пока не подключены к runtime-compose.
- `mcp-rest-api` публикуется через compose port mapping и может быть открыт в LAN через `ADMIN_BIND_HOST` + `ADMIN_PUBLISHED_PORT`.

## Структура

```
infra/
└── compose/
    ├── docker-compose.yml          # текущий runtime-стек
    ├── .env.example                # шаблон переменных окружения
    ├── .env                        # локально/на сервере, не в git
    ├── Caddyfile                   # зарезервирован под будущий reverse-proxy
    └── secrets/
```

## Сервисы

| Сервис             | Image                            | Тип            | Зависит от                  |
|--------------------|----------------------------------|----------------|-----------------------------|
| postgres           | postgres:16                      | datastore      | -                           |
| redis              | redis:7.2-alpine                 | datastore      | -                           |
| neo4j              | neo4j:5-community                | datastore      | -                           |
| qdrant             | qdrant/qdrant:v1.18              | datastore      | -                           |
| xray               | local build                      | service        | -                           |
| telegram-ingestor  | pil/telegram-ingestor (local build) | service     | redis, postgres, внешний S3 |
| ai-orchestrator    | pil/ai-orchestrator             | service        | redis, postgres, Wormsoft/Polza |
| memory-projector   | pil/memory-projector            | service        | redis, postgres, neo4j, S3  |
| embedding-indexer  | pil/embedding-indexer           | service        | redis, qdrant, Wormsoft embeddings |
| mcp-rest-api       | pil/mcp-rest-api                | service        | postgres, redis, neo4j, qdrant |
| maintenance        | pil/maintenance                 | service        | postgres                    |
| migration-runner   | one-off local build             | ops            | postgres, migrations        |

Планируются, но пока не подключены в текущий compose:

- `admin-ui`
- observability stack

## Сети

- `pil-bus` — все сервисы PIL + redis.
- `pil-data` — сервисы PIL + postgres + neo4j + qdrant.
- `pil-ingest` — `xray` + `telegram-ingestor`.

Внешний reverse-proxy через Caddy пока не активирован в compose.
Если нужен прямой LAN-доступ без reverse-proxy, используется publish у `mcp-rest-api`, например `192.168.31.165:80 -> 8090`.

## Healthchecks

Текущие healthchecks:

- `telegram-ingestor`: `GET /healthz` → 200.
- `mcp-rest-api`: `GET /healthz` → 200.
- postgres: `pg_isready`.
- neo4j: HTTP probe на локальный порт.
- qdrant: TCP probe на локальный порт.
- redis: `redis-cli PING`.

Плановый следующий этап:

- отдельные `/healthz` и `/metrics` для всех processors;
- system health endpoint с downstream readiness beyond basic API liveness.

Зависимости `depends_on` с `condition: service_healthy` для критических.

## Volumes

`postgres-data`, `redis-data`, `neo4j-data`, `neo4j-logs`, `qdrant-data`.

В production — bind-mount на отдельный data-диск (см. deployment-proxmox.md).

## Команды

Полный checkout с корневым `Makefile`:

```Makefile
deps
up
down
logs
ps
smoke
migrate
migrate-status
migrate-runtime
deploy-runtime
lint
fmt
typecheck
test
verify
pre-commit-install
```

Текущий server runtime с синхронизированным корневым `Makefile`:

```bash
make migrate-runtime
make deploy-runtime
make ai-backfill
docker compose -f infra/compose/docker-compose.yml ps
docker compose -f infra/compose/docker-compose.yml logs -f
docker compose -f infra/compose/docker-compose.yml up -d
docker compose -f infra/compose/docker-compose.yml down
```

`migration-runner` используется как one-off контейнер для Alembic-миграций и не должен оставаться постоянно запущенным в runtime.

## Secrets management

- Файл `.env` хранится в `infra/compose/` с `chmod 600`, в репо — только `.env.example`.
- Чувствительные данные (`BUSINESS_BOT_WEBHOOK_SECRET`, `JWT_SECRET`, `BOT_TOKEN`, `TELETHON_API_HASH`) — через `secrets:` directive compose v3.7+.
- Для canonical AI runtime дополнительно нужны `WORMSOFT_API_BASE`, `WORMSOFT_API_KEY`, `WORMSOFT_MODEL_DEFAULT`, `WORMSOFT_EMBEDDING_MODEL`; при fallback-маршрутизации также `POLZA_API_BASE` и `POLZA_API_KEY`.
- Никогда не логируем секреты; `libs/observability` имеет filter на маскирование.

## TLS

- `Caddyfile` сохранён как задел под будущий reverse-proxy.
- В текущем runtime-compose TLS-терминация не поднимается автоматически этим файлом.

## Логи

- Все текущие сервисы пишут в stdout/stderr контейнеров.
- Сбор через Loki/promtail остаётся целевым состоянием.

## Метрики

- `/healthz` реализован как минимум у `telegram-ingestor` и `mcp-rest-api`.
- Полноценный `/metrics` и централизованный Prometheus scrape описаны как следующий этап.

## Резервное копирование

- На текущем этапе опираемся на Proxmox snapshots и внешнее S3 raw storage.
- `maintenance` уже подключен для partition housekeeping и cleanup `processed_event`; backup-контур через него ещё не подключён.

## Sanity checks после `up`

```bash
make smoke
```

Сейчас этот wrapper показывает только healthchecks контейнеров.

Для фактической проверки pipeline дополнительно:

- убедиться, что `docker compose ... ps` не показывает `unhealthy`;
- проверить `telegram-ingestor` по `/healthz`;
- **xray + Telegram:** у `telegram-ingestor` healthcheck имеет длинный `start_period` (см. compose): первый `delete_webhook` через HTTP CONNECT к `api.telegram.org` может занимать десятки секунд. При `ProxyTimeoutError` / SSL handshake timeout проверь логи `xray` (accepted к `api.telegram.org`), попробуй `TG_PROXY_URL=socks5://xray:10808` и/или увеличь `TG_API_TIMEOUT_SECONDS`. Локальный прогон: `docker compose exec -i telegram-ingestor python3 - < scripts/probe_telegram_proxy.py` из корня репозитория;
- **Liveness vs readiness:** `delete_webhook` выполняется в той же `asyncio.gather`, что и uvicorn `/healthz`, поэтому healthcheck не ждёт окончания вызова к Telegram (см. `telegram-ingestor` `__main__.py`). Для полной готовности бота при необходимости добавь отдельный `/readyz` с `get_me`.
- отправить тестовое сообщение в allowed chat;
- просмотреть логи `ai-orchestrator`, `memory-projector`, `embedding-indexer`;
- при cutover-проверке дополнительно прогнать `make cutover-audit` и, если у transitional consumer groups `pending=0`, `make cutover-cleanup`.

## Если админка пустая

`mcp-rest-api` может быть `healthy`, но страницы `/admin`, `/admin/people` и `/admin/conversations` всё равно будут почти пустыми, если canonical AI pipeline ещё не сформировал `analysis_window`, `interaction` и `analytics_signal`.

Проверять в таком порядке:

1. Убедиться, что ingestion вообще пишет историю в Redis stream `events.telegram.message`.
2. Проверить, что `ai-orchestrator` читает новые события без ошибок.
3. Если runtime поднят поверх уже существующей истории, выполнить backfill:

```bash
make ai-backfill
```

Эта команда повторно прогоняет `events.telegram.message` через `ai-orchestrator` и наполняет `analysis_window`, `task`, `interaction` и `analytics_signal`.

Практическое замечание:

- если `telegram-ingestor` временно теряет доступ к Telegram и в логах идут `TelegramNetworkError` / timeout, админка не будет обновляться в реальном времени, даже если исторический backfill уже выполнен.
