# Глоссарий

Сквозные термины проекта. Если термин используется в нескольких документах — он должен быть здесь.

## Telegram / привязка бота

- **Chat Automation** — функция Telegram (анонс 7 мая 2026), позволяющая пользователю подключить бота к своему профилю и разрешить ему отвечать в выбранных чатах от имени пользователя. См. reference: `docs/Привязка ботов к аккаунту Telegram*.md`.
- **Business Bot / Business Mode** — режим Bot API, в котором бот обслуживает аккаунт пользователя; источник событий `business_connection`, `business_message`.
- **BusinessConnection** — событие Telegram, означающее, что пользователь подключил/отключил бота к своему профилю; даёт боту список разрешённых чатов.
- **Userbot** — обычный Telegram-аккаунт, к которому подключён клиент по протоколу MTProto (Telethon/Pyrogram). Видит чаты пользователя как сам пользователь.
- **Allowlist** — белый список чатов/контактов, на которые расширено наблюдение PIL.

## Данные и память

- **Person** — запись о человеке (контакте) в Postgres: идентификаторы Telegram, имя/username, роли, организации, стиль общения, trust_score, теги. Каноническая схема — `docs/03-data-model/postgres-schema.md`.
- **Interaction** — резюме переписки (диалогового окна или конкретного эпизода): участники, тема, sentiment, выделенные задачи, ссылка на raw-сообщения.
- **Task / Commitment** — обещание или TO-DO, извлечённое из сообщения. Имеет owner, due date, status, ссылку на исходное сообщение.
- **Relationship Edge** — ребро в графе Neo4j между двумя `Person` (или `Person` ↔ `Organization`). Типы: `mentions`, `works_with`, `boss_of`, `friend`, `co_chat` и т.д. Вес — функция частоты и недавности.
- **Memory Chunk** — единица семантической памяти в Qdrant: текст (summary/note/idea), embedding, payload с метаданными (linked persons, source).
- **Trust score** — производный показатель уверенности в достоверности профиля контакта (на основе частоты общения, источников, явных подтверждений).
- **Retention class** — класс данных по политике хранения (`raw`, `derived`, `graph`, `vector`, `audit`). См. `docs/01-product/privacy-and-compliance.md`.

## Системные компоненты

- **Ingestion Layer** — слой, читающий обновления из Telegram (Telethon userbot и/или Business Bot adapter) и публикующий события в Event Bus.
- **Event Bus** — Redis Streams. Поток-нейминг: `events.telegram.message`, `events.telegram.business_connection`, `events.processing.entity_found`, …
- **Extractor** — обобщённое название для процессингового сервиса (entity, persona, task, summarizer, memory-distiller).
- **Graph Builder** — сервис, который потребляет события и пишет узлы/рёбра в Neo4j (находится в зоне Storage — см. AGENTS.md).
- **Memory Distiller** — сервис, периодически конспектирующий важные события и создающий вектора для долгосрочной памяти.
- **MCP API** — Model Context Protocol сервер: единый endpoint, к которому подключаются внешние LLM и берут «контекст по запросу».
- **GraphRAG retrieval** — комбинированный retrieval: вектор-поиск в Qdrant + graph-walk в Neo4j + структурные запросы к Postgres, выходом отдаёт единый контекст для LLM.
- **DLQ (Dead Letter Queue)** — `<stream>:dlq` — Redis-stream, куда пишутся события, не обработанные после `max_retries`. Должны разбираться вручную через runbook.

## Качество / процессы

- **ADR (Architecture Decision Record)** — короткий markdown-документ в `docs/10-adr/`, фиксирующий архитектурное решение (контекст / варианты / решение / последствия). Шаблон — ADR-0001.
- **Handoff-блок** — стандартная секция в PR/таске, описывающая статус работы для следующего агента. Шаблон — `docs/11-agents/handoff-protocol.md`.
- **Verify** — единая команда контроля качества: lint + type + unit + integration. Запускается локально и в CI.
- **MVP-1 / MVP-2 / MVP-3** — фазы roadmap. MVP-1 — ядро сбора, MVP-2 — граф и семантическая память, MVP-3 — масштабность и продакшен-обвязка.

## Агенты

- **Claude Code / Codex / Cursor** — три инструмента, через которые ведётся разработка. Их характеристики и зоны применимости — `docs/11-agents/`.
- **Handoff** — событие смены агента (или просто закрытия сессии). Подразумевает заполнение handoff-блока.
- **Spec** — маркдаун-документ (PRD / pipeline spec / API spec), на который ссылается тикет; основной артефакт постановки задачи для агента.
- **Tooling capability** — какие инструменты есть у конкретного агента (исполнение bash, чтение файлов, редактирование, превью UI и т.д.).
