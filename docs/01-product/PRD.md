# PRD — Personal Intelligence Layer

Версия: 0.1 (draft, MVP-1 scope зафиксирован, MVP-2/3 — ориентиры).

## 1. Цель продукта

Дать **одному пользователю** (владелец self-host инсталляции) персональный «второй мозг» над Telegram, который автоматически собирает структурированный социальный контекст и делает его доступным внешним LLM-ассистентам.

Метрики ценности:

- сокращение времени на «вспомнить, что я обещал X» — целевой бенчмарк: 0 ручных сводок в Notion за 30 дней эксплуатации;
- покрытие персон: 95% часто-используемых контактов имеют непустой профиль через 14 дней работы;
- precision @ top-5 retrieval по вопросам «что мы обсуждали с X»: ≥ 0.7 на размеченной выборке.

## 2. Целевой пользователь

Один пользователь (см. также [personas-and-jobs.md](personas-and-jobs.md)):

- активно общается в Telegram (≥ 100 значимых контактов, ≥ 1000 сообщений/нед);
- технически подкован, готов поднять Docker Compose и Proxmox;
- ценит приватность выше удобства: дефолт — local-only, облачные LLM — opt-in.

Не-цели MVP-1: команды, мульти-аккаунт, мульти-арендность.

## 3. Сценарии (top-5)

1. **«Что мы обсуждали с Алексеем за последний месяц?»** — пользователь спрашивает LLM в любом интерфейсе, LLM через MCP получает summary + key tasks + ссылки на оригинальные сообщения.
2. **«Что я обещал на этой неделе?»** — LLM возвращает open tasks с deadline по всем контактам.
3. **«Кто из моих контактов работает в Газпроме?»** — graph-query через MCP, ответ из Neo4j + Postgres.
4. **«Подготовь черновик ответа Петру»** — LLM получает persona Петра (стиль общения, последние темы) и пишет в его tone.
5. **«Удали всё про Машу»** — GDPR-like запрос: пользователь нажимает в Admin UI, происходит каскадное удаление во всех хранилищах с подтверждением.

## 4. Функциональные требования

### 4.1 Ingestion

- F-ING-1. Поддерживать Telethon userbot (MTProto) как основной канал. Сессия хранится зашифрованной локально.
- F-ING-2. Поддерживать Business Bot adapter (Bot API) как дополнительный канал. Включается опционально.
- F-ING-3. Allowlist чатов и контактов конфигурируется через Admin UI; ingestion соблюдает его до публикации event.
- F-ING-4. Обновления редактирования и удаления сообщений отслеживаются (`message_edit`, `message_delete`).
- F-ING-5. Поддерживать backfill — однократный импорт последних N сообщений из чата при первой привязке (N — параметр, default 200).

### 4.2 Processing

- F-PROC-1. Entity extractor: NER (имена/орги/локации) + topics. Источник модели — конфигурируемо (local spaCy → cloud LLM).
- F-PROC-2. Persona builder: для каждого контакта строится профиль (tone, frequent topics, role hints, last_active, trust_score).
- F-PROC-3. Task extractor: распознаёт обещания/TODO в сообщениях пользователя и собеседника. Создаёт Task с owner/due/status.
- F-PROC-4. Chat summarizer: пакетно (по N сообщений или по диалоговому окну) формирует Interaction с summary, темами, sentiment.
- F-PROC-5. Memory distiller: формирует Memory Chunk (текст + embedding) для долгосрочной памяти.
- F-PROC-6. Graph builder: пишет Person/Organization/Chat узлы и рёбра (`mentions`, `co_chat`, `works_with`, …) в Neo4j.

### 4.3 Storage

- F-STO-1. Postgres хранит каноническую модель (Person, Interaction, Task, Source, AuditLog).
- F-STO-2. Neo4j хранит граф связей.
- F-STO-3. Qdrant хранит embeddings и payload memory chunks.
- F-STO-4. S3-compatible object storage хранит сырые сообщения, медиа, экспорт.
- F-STO-5. Каскадное удаление по `person_id` затрагивает все хранилища (см. F-FN-PRIV-1).

### 4.4 API / MCP

- F-API-1. MCP-сервер выставляет инструменты: `get_person`, `search_persons`, `get_person_context`, `get_open_tasks`, `search_interactions`, `search_memory`, `graph_walk`.
- F-API-2. REST API дублирует MCP-инструменты и обслуживает Admin UI.
- F-API-3. OpenAPI 3.1 спека генерируется из FastAPI и хранится в `docs/04-api/openapi.yaml`.
- F-API-4. Авторизация: JWT (Admin) + API-key (внешний MCP-клиент).

### 4.5 Admin UI

- F-UI-1. Дашборд статуса (соединения, очереди, последние ошибки, DLQ).
- F-UI-2. Управление allowlist (чаты + контакты).
- F-UI-3. Просмотр persona / interactions / tasks / memory с фильтрами.
- F-UI-4. Настройки моделей и приватности.
- F-UI-5. Кнопка «удалить всё про этого человека» с подтверждением.

### 4.6 Приватность

- F-FN-PRIV-1. Любое сырое сообщение должно быть удаляемо по запросу, каскад — везде.
- F-FN-PRIV-2. Сырые сообщения уходят в облачные LLM только при явном opt-in (per-pipeline).
- F-FN-PRIV-3. Локальный режим (только local LLM + embeddings) должен работать без интернета.
- F-FN-PRIV-4. Audit log фиксирует каждое чтение через MCP с указанием каллера (api-key).

## 5. Нефункциональные требования

- NFR-1. Latency end-to-end ingestion → запись фактов ≤ 30 сек (P95) для текстового сообщения ≤ 1000 знаков.
- NFR-2. Доступность Admin UI: best-effort, single-node допустимо.
- NFR-3. Throughput: 50 событий/сек устойчиво на 4 vCPU / 16 GB RAM на узле Proxmox.
- NFR-4. Хранение: дефолтный ретеншен сырых сообщений = 90 дней; derived (Persons/Tasks/Interactions) — без TTL.
- NFR-5. Безопасность: секреты только через env/secret-mounts; БД-доступ только по сети docker compose.
- NFR-6. Восстановление: RPO ≤ 24ч, RTO ≤ 2ч из ежедневного снапшота.
- NFR-7. Языки сообщений: RU + EN обязательно, остальное — best-effort.

## 6. Acceptance criteria по фазам

См. [docs/09-roadmap/](../09-roadmap/) для детальных AC. Здесь — резюме:

- **MVP-1 release gate.** Bot подключается, allowlist редактируется, Persons/Tasks/Interactions появляются в Admin UI, MCP-инструмент `get_person_context` возвращает осмысленный JSON.
- **MVP-2 release gate.** GraphRAG retrieval бьёт baseline на 20%+ по precision@5 на разметке, Qdrant и Neo4j подключены, retention-jobs работают.
- **MVP-3 release gate.** Monitoring (Prometheus+Grafana), backup/restore проверены, multi-account scaffold (без полного UI).

## 7. Открытые вопросы

- Q-PRD-1. Стоит ли поддерживать множественные Telegram-аккаунты под одним инстансом PIL уже на MVP-2? — оценить cost-of-delay.
- Q-PRD-2. Делать ли «proactive notifications» (бот сам пишет владельцу «у тебя 3 невыполненных обещания»)? — UX-риск.
- Q-PRD-3. Использовать ли нативный Telegram-mini-app для Admin UI вместо/в дополнение к web? — пользователь-эргономика vs усложнение деплоя.

Открытые вопросы трекаются в [docs/09-roadmap/milestones.md](../09-roadmap/milestones.md).
