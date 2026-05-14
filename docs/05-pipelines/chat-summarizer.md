# Pipeline: Chat Summarizer

`services/chat-summarizer` — собирает скользящие резюме (Interaction) по диалогам/группам.

## Цель

Каждый чат должен иметь живую цепочку Interaction'ов — компактный пересказ окон активности с темами, sentiment и списком задач.

## Стратегии разбиения

Выбирается per chat в Admin UI:

- **`by_count`** — каждые N сообщений (дефолт 50).
- **`by_time_window`** — каждые T минут активности (дефолт 60 мин, gap 30 мин = новый Interaction).
- **`by_thread`** — для групп: считать каждую reply-цепочку отдельным эпизодом (через `tg_reply_to_message_id`).
- **`hybrid`** — комбинация by_thread + by_time_window.

## Вход

- `events.telegram.message` — сообщения для текущего окна.
- `events.telegram.message_edited` — пересчёт затронутого Interaction.

## Выход

- Postgres: UPSERT `interaction`.
- S3-compatible object storage: `interaction-windows/<interaction_id>.json` — сырое окно сообщений (для повторного re-summarize).
- Поток: `events.processing.interaction_updated`.

## Алгоритм

1. Накопить окно в Redis (`pil:summarizer:<chat_id>:window`).
2. Когда trigger удовлетворён — сериализовать окно → object storage.
3. Сгенерировать summary:
   - **MVP-1**: эвристика (топ-N tf-idf фраз + first/last message + список participants).
   - **MVP-2**: `libs/llm-client` с structured output. Текущий cloud backend — Wormsoft (`WORMSOFT_API_BASE`, `WORMSOFT_API_KEY`, `WORMSOFT_MODEL_DEFAULT`):
     ```
     { topics: string[], sentiment: enum, summary: string (≤ 350 chars), tasks: string[] (≤ 5) }
     ```
4. Извлечённые tasks связываются с уже созданными в `task` (по сходству title) или создаются (передаются в `task-extractor`-канал как hint).
5. UPSERT `interaction`. Список `participants` — UUID персон, найденных в окне.

## Idempotency

- Key окна = `(chat_id, window_start)`; повторный апдейт переписывает summary.

## Конфигурация

```
SUMMARIZER_STRATEGY=by_count
SUMMARIZER_WINDOW_SIZE=50
SUMMARIZER_TIME_WINDOW_MINUTES=60
SUMMARIZER_LLM_MODE=local|cloud|hybrid
SUMMARIZER_MAX_TOKENS_OUT=400
```

## Качество

- Метрика — ROUGE-L против reference-summaries на размеченной выборке (см. `tests/fixtures/summaries_gold.json`).
- В CI — guard: regression > 5% → fail.

## Observability

- `pil_summarizer_windows_total{strategy}`
- `pil_summarizer_llm_tokens_total{mode}`
- `pil_summarizer_lag_seconds`

## Тесты

- Unit — выбор стратегии, обработка edge cases (1 сообщение, всё на одном языке, mixed RU+EN).
- Snapshot — golden summaries.
- Integration — поток events → interaction в Postgres.

## Open questions

- Q-SUM-1. Делать ли «топик-aware» summarizer (разбивать окно по сменам темы внутри)? MVP-2 эксперимент.
- Q-SUM-2. Хранить ли несколько версий summary (если стратегия меняется или модель апдейтится)?
