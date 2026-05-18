# Backups & retention

## Принципы

- **Два независимых уровня бэкапов.** Proxmox-снапшоты VM + логические бэкапы внутри стека. Восстановление из любого.
- **Шифрованные артефакты.** Для raw/object storage сейчас используется S3 cloud.ru; автоматизированный backup-bucket ещё предстоит дособрать.
- **RPO ≤ 24ч, RTO ≤ 2ч.**
- **Регулярная проверка восстановления.** Раз в месяц — restore-drill на test VM.

## Логические бэкапы

Целевой контур: `services/maintenance` запускает cron-job ежесуточно в 02:00 (UTC).

Текущее состояние на 2026-05-12:

- `services/maintenance` уже поднят и выполняет baseline-housekeeping:
  - создаёт партиции `interaction`, `processed_event`, `audit_log` на месяц вперёд;
  - подчищает `processed_event` по retention;
- автоматический backup-job через `services/maintenance` ещё не подключён;
- основной рабочий механизм — Proxmox snapshots VM;
- raw payloads уже лежат во внешнем S3 cloud.ru, но это не заменяет полные логические бэкапы Postgres/Neo4j/Qdrant.

Целевой набор бэкапов:

| Объект           | Команда                                                       | Размер (оценка) |
|------------------|---------------------------------------------------------------|-----------------|
| Postgres         | `pg_dump -Fc --no-acl --no-owner pil` → gzip                  | ~100–500 MB     |
| Neo4j            | `neo4j-admin database dump pil --to-path=...`                 | ~50–200 MB      |
| Qdrant           | `POST /collections/<c>/snapshots` для каждой коллекции        | ~500 MB – 5 GB  |
| Object storage   | mirror объектов `raw/` за прошлые сутки на NAS                | ~ 100 MB – N GB |

Результат должен складываться в bucket `backups/<yyyy-mm-dd>/`.

Retention бэкапов — `setting.backup.retention_days` (дефолт 30).

## Проверка восстановления (drill)

Целевой drill-script: `scripts/ops/restore_drill.sh`.

1. Создать чистый Docker Compose stack в namespace `pil-drill`.
2. Скачать вчерашний бэкап.
3. Применить:
   - `pg_restore` в pristine Postgres;
   - `neo4j-admin load`;
   - upload qdrant snapshots + `POST /collections/<c>/snapshots/<file>/recover`;
   - sync object-storage objects.
4. Запустить `make smoke` против drill-стэка.
5. Удалить drill-стек.

Drill — раз в месяц, результаты в audit-log как `system.backup.drill`.

## Retention сырых данных

- `setting.retention.raw_message_days` (дефолт 90).
- Bucket `raw` в object storage имеет lifecycle policy:
  ```json
  { "Rules": [{ "ID": "raw-expire", "Status": "Enabled", "Expiration": { "Days": 90 } }] }
  ```
- `services/maintenance` параллельно подчищает связки в Postgres (`raw_object_key` → NULL).

## Retention derived данных

- `task.status='done'` старше 365 дней → удаляются.
- `interaction` старше N лет — опц. (по умолчанию хранятся бессрочно).
- `memory_chunk` старше `setting.retention.memory_chunk_days` (дефолт 365) — удаление через `delete by filter` в Qdrant + связки.

## Каскадное удаление (GDPR)

Триггер — `DELETE /v1/persons/{id}/erase` или operator action в админке. Текущее состояние runtime на `2026-05-19`:

1. Postgres: каноническое удаление `person`, связанных `analysis_window`, `analytics_signal`, `extracted_fact`, `interaction`, `task`; FK-каскады дочищают `chat_membership`, `mention`, `relationship_annotation`.
2. Neo4j: `MATCH (p:Person {id:$1}) DETACH DELETE p`.
3. Qdrant: `delete by filter(payload.person_ids contains $1)` по активному alias.
4. Object storage: best-effort удаление `interaction`-artifact keys из canonical `source_object_ref`.
5. Audit: `system.erase.person` с pseudonymized id (sha256(id)).

Всё под одной транзакцией невозможно (multi-store), поэтому используется **saga** с retry semantics: канонический delete фиксируется первым, derived cleanup идёт best-effort и записывает warnings в результат job/audit.

Оставшийся hardening:

- durable job persistence, а не только in-process job store в `mcp-rest-api`;
- полное удаление raw ingress objects, когда pipeline начнёт хранить per-person object refs/tagging в canonical слое.

## Audit и compliance

- Audit-log хранится не менее 365 дней.
- При запросе на удаление контакта старые audit-записи **не удаляются**, но id заменяется на хеш.

## Восстановление в production

1. Решение «откатить» — оператор (Owner).
2. Если `snapshot-all` wrapper появится — использовать его; пока фиксируем текущее состояние вручную.
3. Зависимо от сценария:
   - **полный rollback** → Proxmox restore VM из снапшота;
   - **частичный** → restore конкретного хранилища из backup-артефакта, когда maintenance-контур будет введён.
4. Прогнать `make verify` и `make smoke`.
5. Сообщение в audit-log: `system.restore`.

## Open questions

- Q-OPS-1. Перейти на Borg/Restic для логических бэкапов вместо текущего object-storage контура (дедупликация даст экономию)? — оценим в MVP-3.
- Q-OPS-2. Делать ли offsite-копию бэкапов (Backblaze B2 / R2) с шифрованием на клиенте? — privacy vs disaster recovery.
