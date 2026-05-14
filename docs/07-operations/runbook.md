# Runbook

Конкретные действия на типовые инциденты. Каждая секция — what / why / fix.

## Healthchecks красные

### Symptom
Сервис в `make ps` показывает `unhealthy`.

### Действия
1. `docker compose -f infra/compose/docker-compose.yml logs <name>` — найти `level=error`, traceback.
2. Если БД-зависимость недоступна:
   - `docker compose -f infra/compose/docker-compose.yml logs postgres`,
   - `docker compose -f infra/compose/docker-compose.yml logs neo4j`,
   - `docker compose -f infra/compose/docker-compose.yml logs qdrant`,
   - `docker compose -f infra/compose/docker-compose.yml logs redis`,
   - проверить free disk (`df -h` на data-VM).
3. Если LLM не отвечает (cloud rate-limit / down):
   - переключить `setting.llm.mode.<pipeline>` в `local`,
   - проверить логи `pil_llm_*`.
4. После починки — restart затронутого сервиса `docker compose -f infra/compose/docker-compose.yml restart <name>`.

## DLQ растёт

### Symptom
`pil_dlq_total{stream}` > 0.

### Действия
1. Открыть `UI → System → Queues → <stream>:dlq`.
2. Посмотреть top-5 событий, причину.
3. Классифицировать:
   - **Bug в коде.** Создать тикет, поправить, передеплоить, кнопка `Retry`.
   - **Battle event (некорректный payload).** Если уверены — `Drop` + audit.
   - **Зависимость лежит.** Поднять зависимость, `Retry`.

## Лаг ingestion → end-to-end > 60 сек

### Действия
1. Dashboard «Overview» → латэнсы по сервисам.
2. Найти боттл-нек:
   - Telethon — flood wait (логировать `pil_ingest_floodwait_total`).
   - LLM extractor — slow inference. Переключить mode на `local` или уменьшить `*_BATCH_SIZE`.
   - Qdrant — slow upsert. Проверить дисковое I/O.
3. Если боттл-нек — Postgres, проверить `pg_stat_activity` (idle connections, long queries).

## Postgres connections исчерпаны

### Symptom
`pil_db_pool_in_use{db='postgres'}` ≈ pool max.

### Действия
1. `select * from pg_stat_activity where state != 'idle' order by query_start asc;`
2. Найти долгие запросы. Если query из `libs/retrieval` — добавить тест на регрессию.
3. Увеличить `POSTGRES_MAX_CONNECTIONS` и pool size — временно. Долговременно — оптимизация SQL.

## Disk free < 10%

### Действия
1. `du -sh /var/lib/docker/volumes/*` — найти жирный том.
2. Обычно — `raw` в object storage или Qdrant `memory_chunks`.
3. Подкрутить retention (`setting.retention.raw_message_days` → меньше), запустить `services/maintenance` cleanup-job вручную.
4. Если Qdrant — рассмотреть `on_disk=true` (уже включено) и compaction.

## Telethon потерял сессию

### Symptom
Логи `AuthKeyUnregisteredError`.

### Действия
1. `Connections → Telethon → Re-auth`.
2. Если QR-код не помогает — Telegram заблокировал сессию. Создать новую `/secrets/telethon.session`, удалить старую.
3. Audit: `system.connection.reauth`.

## Business webhook 4xx/5xx

### Действия
1. `make logs SERVICE=telegram-ingestor | grep webhook`.
2. Если 401 — сменился `BUSINESS_BOT_WEBHOOK_SECRET`, синхронизировать с Telegram.
3. Если 5xx — приложение упало; рестарт + traceback в issue.

## Все смуки красные после деплоя

### Действия
1. Если появится `snapshot-all` wrapper — использовать его; пока зафиксировать текущее состояние вручную.
2. Если есть git-checkout — `git revert <bad-commit>` или `git checkout <prev-tag>`.
3. Если на сервере только runtime working tree без `.git` — вернуть последний known-good snapshot файлов и/или восстановиться из Proxmox snapshot.
4. Откатить миграцию только вручную и только если она обратима.
5. `make up` + `make smoke` или эквивалентные команды вручную.

## GDPR-каскад завис

### Symptom
Job на `/v1/persons/{id}/erase` в статусе `running` > 10 минут.

### Действия
1. `GET /v1/jobs/{id}` — где он стоит.
2. Если зависает на Qdrant — `qdrant-client` retry (`delete by filter` иногда таймаутится при больших коллекциях).
3. После решения — job идемпотентен, перезапуск через `POST /v1/jobs/{id}/retry`.

## Audit log переполнен

### Действия
1. `setting.audit.retention_days` — увеличить retention если нужно сохранить.
2. `services/maintenance` планируется с ежемесячным job сжатия audit-log в gz-архивы в object storage.

## Privacy pre-release checklist

Перед каждым релизом:

- [ ] cascading delete покрыт integration-тестом и тест зелёный;
- [ ] opt-in переключатели реально гейтят cloud LLM (e2e тест с моком сети);
- [ ] backup создаёт зашифрованный артефакт;
- [ ] restore drill отработан ≤ 30 дней назад;
- [ ] версия зависимостей не содержит известных CVE (см. CI gate);
- [ ] обновлены `docs/01-product/privacy-and-compliance.md` и `docs/03-data-model/*` если менялись схемы.

## Контакты

- Owner: ты сам.
- Logbook: `docs/09-roadmap/milestones.md` секция «Incidents».
