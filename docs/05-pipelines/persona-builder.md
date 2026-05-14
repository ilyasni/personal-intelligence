# Pipeline: Persona Builder

`services/persona-builder` — поддерживает актуальный `Person`-профиль на основе входящих сообщений и результатов entity-extraction.

## Цель

Для каждого человека (включая владельца) собрать:

- **identity**: display_name, username, alternative names (никнеймы, фамилии);
- **organizations**: где работает / связан;
- **role hints**: «продакт», «дизайнер», «инвестор», …;
- **communication style** (1 предложение);
- **frequent topics** (top-N);
- **trust_score** (0–1);
- **last_interaction_at**, **last_topics**.

## Вход

- `events.telegram.message` (для контекста сообщений)
- `events.processing.entity_found` (готовые кандидаты)

## Выход

- Postgres: UPSERT в `person` со слиянием polей.
- Qdrant: `person_summaries` collection — embedding профиля целиком (для запросов «найди похожего контакта»).
- Поток `events.processing.person_updated` (опц., для UI live-updates) — MVP-2.

## Алгоритм

1. **Группировка.** Накопить N сообщений или T минут активности по person — micro-batch.
2. **Reconciliation.** Сопоставить кандидата (имя/username) с существующим Person; merge при подтверждении (2+ сигнала: общий чат + похожее имя).
3. **Style summary.** Через `libs/llm-client` (или эвристика для MVP-1):
   - средняя длина сообщения;
   - доля emoji;
   - частые conversational markers (формальный/неформальный);
   - 1-предложение style (LLM, если cloud разрешён).
4. **Topics.** Топ-K из `mention` + `topic` за окно N дней.
5. **Organizations / role.** Из entity-результатов + LLM-валидация (опц.).
6. **Trust score.** Формула (черновик):
   ```
   trust = 0.3 * recency_score + 0.3 * frequency_score + 0.2 * consistency_score + 0.2 * mutual_score
   ```
   - `recency_score`: e^{-days_since_last/30}
   - `frequency_score`: log(1 + msg_count_30d) / log(200)
   - `consistency_score`: насколько стабильны temaы (низкая дисперсия топиков)
   - `mutual_score`: есть ли исходящие сообщения от владельца к этому person
7. **Embedding persona summary.** Конкатенация ключевых полей → embedding → upsert в `person_summaries`.

## Idempotency

- `consumer_name='persona-builder'`. Каждое сообщение засчитывается один раз.
- Сам апдейт `person` — UPSERT (`ON CONFLICT DO UPDATE`).

## Конфигурация

```
PERSONA_BATCH_SIZE=20
PERSONA_BATCH_TIMEOUT_SECONDS=120
PERSONA_TOPICS_WINDOW_DAYS=30
PERSONA_LLM_MODE=local|cloud|hybrid
```

## Observability

- `pil_persona_updates_total`
- `pil_persona_llm_tokens_total{purpose}`
- `pil_persona_reconcile_merges_total`

## Тесты

- Unit — формула trust, reconcile.
- Snapshot — golden case: «дано 20 сообщений, ожидаемый Person-снимок».
- Integration — Postgres + Qdrant.

## Open questions

- Q-PER-1. Хранить ли историю изменений профиля (event-sourcing)? — даст откат, но удорожает.
- Q-PER-2. Разрешать ли владельцу вручную править style/role (override)? — MVP-2.
