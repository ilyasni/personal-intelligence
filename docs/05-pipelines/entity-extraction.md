# Pipeline: Entity Extraction

`services/entity-extractor` — извлекает именованные сущности (persons, organizations, places) и темы из текста сообщения.

## Вход

- Поток: `events.telegram.message`
- Только текст и подписи к медиа. Голосовые/видео обрабатываются после прогона через STT (MVP-3).

## Выход

- Поток: `events.processing.entity_found`.
- Postgres:
  - `mention` — для упоминаний person↔person.
  - `topic` — нормализованные темы.
  - обновление `person.topics`, `person.organizations` (через persona-builder, но entity-extractor пушит сырые candidate'ы).

## Алгоритм (MVP-1)

1. **Препроцессинг.** Lowercase, замена ссылок/email/phone токенами, склейка emoji.
2. **NER через spaCy.** Модель — `ru_core_news_lg` (RU), `en_core_web_lg` (EN). Авто-детект языка через `fasttext-langid`.
3. **Topics.** TF-IDF по словарю + LLM-проверка для топ-3 кандидатов (если включён cloud mode).
4. **Person reconciliation.** Кандидат на person сначала ищется в Postgres:
   - точное совпадение `username`/`display_name`;
   - похожесть Левенштейном ≥ 0.85;
   - если нашли — `person_id = found`; иначе candidate без id (создание Person — отдельный шаг через persona-builder).
5. **Organization reconciliation.** Slug = transliterate + slugify; если slug совпадает — same org.
6. **Publish.** `entity_found` событие на шину.

## Алгоритм (MVP-2)

- LLM как primary extractor с structured output (через function calling). spaCy — fallback и проверка.
- Hybrid: spaCy сначала, LLM уточняет на низко-confidence кандидатах.

## Конфигурация

```
ENTITY_MODE=local|cloud|hybrid
ENTITY_MIN_CONFIDENCE=0.6
ENTITY_BATCH_SIZE=16
ENTITY_LLM_MODEL=anthropic:claude-haiku|openai:gpt-4o-mini|local:llama3
```

## Idempotency

- `consumer_name='entity-extractor'`.
- Перед обработкой — `processed_event` check.

## Failure modes

- **spaCy crash на edge-case.** Catch, перевод в DLQ.
- **LLM 5xx.** Retry с backoff (см. shared-conventions). На исчерпании — DLQ.
- **Очень длинное сообщение.** Чанкуем по 500 токенов, объединяем результаты (дедупликация по surface form).

## Observability

- `pil_entity_messages_total{language}`
- `pil_entity_extracted_total{kind}` (`person`, `organization`, `topic`)
- `pil_entity_llm_tokens_total{model}` (если cloud).

## Тесты

- Unit — функции normalization, reconciliation.
- Snapshot — golden-fixture сообщений → ожидаемые entities.
- Integration — на seed-Postgres проверить, что `mention` пишется и Person reconcile работает.

## Open questions

- Q-ENT-1. Делать ли отдельный `place_mentions` (для путешествий) уже в MVP-1?
- Q-ENT-2. Где грань между «темой» и «организацией»? — нормализуем через `topic.slug` vs `organization.slug`.
