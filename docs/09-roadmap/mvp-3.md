# MVP-3: производственная зрелость

**Цель**. Превратить рабочий self-host в стабильный продакшен на длительной горизонт: масштабируемость, наблюдаемость, мульти-аккаунт, media.

**Длительность**: 8–12 недель, опционально по фичам.

## Scope (опц., каждый блок включается отдельно)

В:
- (опц.) Kubernetes (k3s) деплой как альтернатива compose.
- Multi-account scaffold: namespace-per-tenant в storage слое.
- Speech-to-text: voice messages → текст → стандартный pipeline.
- Image OCR (опц.): фото с текстом → текст.
- Vault для секретов.
- Alerting через webhook в Telegram-канал owner-а.
- Proactive nudges (опц., feature flag): «у тебя 3 невыполненных обещания» — раз в день.
- Push notifications через WebSocket в UI.
- Cross-language: расширить entity-extractor на не RU/EN языки.

Не в:
- Полноценный SaaS / биллинг.
- Public registry (плагины).

## Тикеты по блокам

### Block A: K8s (опц.)
- A-01. Helm charts для всех сервисов.
- A-02. StatefulSets для postgres / neo4j / qdrant / minio с PVC.
- A-03. Ingress + cert-manager.
- A-04. Vault + external-secrets.
- A-05. Миграция данных compose → k3s (drain & restore).

### Block B: Multi-account
- B-01. Namespace в Postgres схемах (per-tenant): `tenant_id` колонка везде + RLS policies.
- B-02. Neo4j: graph database-per-tenant (Neo4j 5 поддерживает).
- B-03. Qdrant: collection naming `pil_<tenant>_memory_chunks`.
- B-04. UI: auth с выбором tenant.
- B-05. MCP API-key привязан к tenant.

### Block C: Media
- C-01. STT через Whisper (local) с очередью для тяжёлых файлов.
- C-02. OCR через Tesseract / RapidOCR для скриншотов.
- C-03. Безопасное хранение медиа: per-tenant bucket, лимиты.

### Block D: Observability
- D-01. OpenTelemetry tracing включён в продакшен, Tempo в стэк.
- D-02. Alertmanager с rules в Prometheus.
- D-03. Telegram-канал owner-а как алёрт-канал.
- D-04. Cost dashboards (cloud LLM USD per day).

### Block E: UX полировка
- E-01. Proactive nudges (с feature flag).
- E-02. Push-уведомления через WebSocket в UI.
- E-03. Mini-app Telegram bot для quick recall (опц., см. PRD Q-PRD-3).
- E-04. PWA-режим Admin UI.

### Block F: Performance
- F-01. Redis Cluster или NATS JetStream (если упремся в Redis Streams).
- F-02. Connection-pool tuning на основе load-test.
- F-03. Кеш-слой `libs/cache` использован в hot retrieval-путях.

## Acceptance criteria (per block)

- [ ] K8s: миграция выполнена без потери данных, smoke зелёный.
- [ ] Multi-account: 2+ изолированных tenant, RLS не пропускает данные между ними.
- [ ] Media: голосовое из чата появляется в `interaction` с транскрипцией.
- [ ] Tracing: traceid пробрасывается end-to-end и виден в Tempo.
- [ ] Alerts: тест-инцидент породил сообщение в Telegram-канале.

## Риски

- K8s удорожает эксплуатацию для одного пользователя; стоит делать, только если есть план роста.
- STT requires GPU для приемлемой производительности — пересмотр железа на Proxmox.
- Proactive nudges чреваты UX-fatigue → тщательное тестирование на себе.
