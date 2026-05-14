# Monitoring

Prometheus + Grafana + Loki. Простая конфигурация, без алёртинг-провайдера на MVP-1.

## Метрики (Prometheus)

Каждый сервис экспортит `/metrics`. Базовый набор:

- `pil_<service>_requests_total{path, status}` (для FastAPI)
- `pil_<service>_event_processed_total{stream, status}` — для consumer'ов
- `pil_<service>_event_processing_seconds` (histogram)
- `pil_<service>_dlq_total{stream}` — gauge, число событий в DLQ
- `pil_llm_tokens_total{model, mode, purpose}` — токены LLM
- `pil_llm_cost_usd_total{model}` — оценочная стоимость (для cloud)
- `pil_db_pool_in_use{db}`
- стандартные `process_*` и `python_gc_*` из `prometheus_client`.

## Дашборды (Grafana)

Папка `infra/grafana/dashboards/`:

1. **Overview** — health всех сервисов, queue length, latency end-to-end ingestion → entity.
2. **Ingestion** — события из Telegram, lag, ошибки.
3. **Processing** — события по extractor'ам, success rate, LLM tokens.
4. **Storage** — Postgres connections, Neo4j heap, Qdrant collection sizes.
5. **MCP usage** — кто запрашивает (по `api_key`), сколько контекста отдано.
6. **Costs** — кумулятивные LLM-токены и USD (если cloud-mode включён).

## Логи (Loki)

- Все сервисы пишут JSON в stdout.
- promtail → Loki.
- Стандартные поля: `level`, `ts`, `service`, `trace_id`, `event_id`, `message`, `error`.
- В Grafana — Explore с фильтрами по `service` и `trace_id`.

## Tracing (опц., MVP-2)

- OpenTelemetry SDK + OTLP экспортёр.
- Контейнер `tempo` или `jaeger-all-in-one` в опц. compose-override.
- В Loki — `trace_id` пробрасывается из ingestion-события.

## Алёрты

MVP-1 — никаких внешних провайдеров; алёрты в Grafana UI:

- DLQ > 0 на любом потоке (warning) или > 10 (critical).
- end-to-end ingestion latency P95 > 60 сек (warning).
- сервис healthcheck падает (critical).
- LLM-токены/сутки > N (warning).
- Free disk < 10% на data-VM (critical).

MVP-3 — opt-in webhook в Telegram-канал owner-а.

## Что смотреть, когда что-то не так

- **Сообщения не появляются.** Dashboard «Ingestion» → если события идут, проблема в extractor'ах; если нет — Telethon/business webhook.
- **Очередь растёт.** Dashboard «Processing» → найти отстающий consumer, проверить LLM latency (cloud rate-limit?).
- **MCP отвечает медленно.** Dashboard «Storage» → Qdrant/Neo4j p95, Postgres connections.

Runbook на каждый сценарий — [runbook.md](runbook.md).
