# Pipeline: Task Extractor

`services/task-extractor` — выделяет обещания, TODO, дедлайны и создаёт `Task`.

## Вход

- `events.telegram.message` — основной источник.
- `events.telegram.message_edited` — пересчёт задачи, если редакция меняла суть.
- `events.telegram.message_deleted` — если удалили сообщение-источник, помечаем task `dropped` (с пометкой `evidence_lost`).

## Выход

- Postgres: `task` (новые), апдейты статусов.
- Поток `events.processing.task_created`, `events.processing.task_resolved`.

## Алгоритм

### Rule-based first pass (MVP-1)

Простые маркеры:

- Глаголы будущего/обещаний (RU): «сделаю», «пришлю», «отправлю», «закину», «согласую», «уточню», «давай к…»
- EN: «will send», «I'll prepare», «let me check», «by Friday», «EOD».
- Маркеры дедлайна: даты, дни недели, «к завтра», «через 2 часа», «EOW/EOM».
- Маркеры to-do (входящие): «нужно», «надо», «давай ты…», «отправь мне».

Извлекаем кандидата `Task` со следующими полями:

- `title` — короткая нормализация (≤ 80 символов).
- `description` — оригинальный фрагмент.
- `owner_person_id` — кто обещает.
- `counterpart_person_id` — кому.
- `due_at` — если найден дедлайн (parser через `dateparser`).
- `priority` — дефолт 3.
- `confidence` — 0.5 для rule-based.

### LLM pass (MVP-2)

- Если включён `TASK_LLM_MODE=cloud|hybrid`, кандидаты с `confidence < 0.7` отправляются в LLM (с structured output).
- LLM возвращает `is_task`, `title`, `owner`, `due_at`, `confidence`.

### Resolution

`task_resolved` детектится через:

- ответный паттерн («сделал», «вот ссылка», «готово»);
- статус-маркеры в чате (`@user done`);
- ручной апдейт через UI.

При resolution создаём событие `task_resolved` + обновляем `task.status = 'done'`, `resolved_at`.

## Idempotency

- `event_id` сообщения → дедуп.
- Каждый `Task` имеет `source_message_ref`; повторная экстракция из того же сообщения возвращает существующий task.

## Конфигурация

```
TASK_RULES_PATH=/etc/pil/task_rules.yaml
TASK_LLM_MODE=local|cloud|hybrid
TASK_MIN_CONFIDENCE=0.4
TASK_DEDUP_WINDOW_HOURS=12
```

## Observability

- `pil_task_extracted_total{source=rule|llm}`
- `pil_task_resolved_total{reason}`
- `pil_task_false_positive_total` (если в UI помечен ложно — см. feedback loop).

## Feedback loop

- В UI пользователь может пометить task как «не было обещания» → `task_extractor` сохраняет этот фрагмент в `tests/fixtures/negative_examples/` (опц.) и логирует counter.

## Тесты

- Unit — rule-based парсер на N golden фразах.
- Snapshot — для diverse-выборки.
- Integration — pipeline: message → task в Postgres, resolution → status='done'.

## Open questions

- Q-TSK-1. Делать ли «бот напомнит про обещание за день до due»? Это уже proactive — см. PRD Q-PRD-2.
- Q-TSK-2. Поддерживать ли recurring («каждую пятницу пришлю отчёт»)? — MVP-2.
