# UX flows

Ключевые пользовательские сценарии. Каждый — со step-by-step и acceptance criteria. Это база для Playwright e2e.

## Flow 1. Первый запуск и инициализация Owner

1. Owner открывает `https://pil.local`.
2. Видит экран «Welcome» с кнопкой «Set up».
3. Шаг 1: задать пароль (12+ символов).
4. Шаг 2: настроить TOTP (показ QR + проверка 6-значного кода).
5. Шаг 3: подтверждение приватности (галочка «Я понимаю, что бот наблюдает за моими чатами» + ссылка на privacy-and-compliance).
6. Редирект на `/dashboard` с пустыми карточками.

AC:
- Без TOTP вход невозможен.
- Backup-коды показываются 1 раз с возможностью скопировать/скачать.

## Flow 2. Привязка Telethon userbot

1. `Connections → Add → Telethon userbot`.
2. Вводит API_ID и API_HASH (получены на my.telegram.org).
3. Сервер показывает QR-код в UI; параллельно начинает Telethon login flow.
4. Owner сканирует QR в Telegram.
5. Если 2FA включена — UI просит пароль.
6. После успеха — статус «Connected», список доступных чатов появляется в `Connections → Allowlist`.

AC:
- Сессия сохраняется в `/secrets/telethon.session` с правами `0600`.
- Lost auth → UI показывает «Re-auth needed» и кнопку повторить.

## Flow 3. Привязка Business Bot

1. Owner создаёт бота в @BotFather, включает Business Mode.
2. В UI `Connections → Add → Business Bot` вводит BOT_TOKEN.
3. Сервер выставляет webhook (`/tg/business-webhook`) — UI показывает URL и секрет.
4. Owner в Telegram идёт в `Settings → Chat Automation → @MyAssistantBot → Allow → выбирает чаты`.
5. Telegram шлёт `business_connection` → UI обновляется (карточка «Bot connected, 12 chats allowed»).

AC:
- Если webhook 4xx — статус «Error», лог в `system.errors`.

## Flow 4. Настройка allowlist чатов

1. `Connections → Allowlist`. Список чатов с фильтром по типу (private / group / supergroup).
2. Toggle на чате → patch.
3. Появляется баннер «Backfill 200 last messages?» — да/нет.
4. Если да — генерируется `system.command{kind:'backfill_chat'}`. UI показывает прогресс.

AC:
- Backfill не блокирует UI.
- При отключении чата перестают приходить новые события (но старые данные остаются — отдельная кнопка «Erase data for this chat»).

## Flow 5. Просмотр карточки Person

1. `Persons → Search «Алексей»` → клик.
2. Карточка: Overview видим сразу; вкладки lazy.
3. Tab `Interactions` — virtual scroll, by date desc.
4. Tab `Graph` — react-flow с 1-hop соседями. Click на node → переход на их карточку.
5. Кнопка «Recall» → modal → ввод вопроса → результат с цитатами + ссылки на оригинальные сообщения.

AC:
- Загрузка карточки ≤ 800 мс P95 на seed-данных.

## Flow 6. Каскадное удаление Person

1. Карточка → kebab menu → «Erase».
2. Modal-warning: «Вы уверены? Это удалит:
   - все persona data,
   - все mentions,
   - все memory chunks,
   - все raw сообщения, где этот person отправитель,
   - все tasks как owner/counterpart.
   Это необратимо.»
3. Ввод подтверждения (печатать display_name).
4. POST `/v1/persons/{id}/erase` → 202 + job id.
5. UI редирект на `/system/jobs/{id}` с прогрессом.
6. По завершении — toast «Erased», audit-log запись.

AC:
- Если job упал — статус `failed` + причина; данные не повреждены (idempotent retry).

## Flow 7. Запрос recall из UI

1. `Memory → Recall`.
2. Поле: «Что обсуждали с Петром по дизайну машины?»
3. Selectors: scope (everyone | person | chat), date range.
4. Submit → POST `/v1/memory/recall` → ответ + список citations.
5. Клик на citation → переход на источник.

AC:
- Если LLM cloud-mode выключен и query тяжёлый — UI показывает honest предупреждение, что recall работает локально.

## Flow 8. Управление API-key для внешнего LLM

1. `Settings → API keys → New`.
2. Имя + scopes (`read`, `mutate`).
3. UI показывает ключ единожды, кнопка «Copy».
4. Owner вставляет в Claude Desktop / Cursor / куда угодно как MCP credential.

AC:
- Повторный показ невозможен.
- Revoke в один клик; новые запросы немедленно начинают возвращать 401.

## Flow 9. Тушение DLQ

1. `System → Queues` → красный бейдж на `events.processing.entity_found:dlq` (count > 0).
2. Клик → таблица событий с `error`, `attempts`, `traceback`.
3. Действия: `Retry`, `Inspect payload`, `Drop`.
4. Retry — XADD обратно в основной поток.

AC:
- Все действия — audit-log.

## Flow 10. Privacy review (раз в N дней — рекомендованно)

1. `Settings → Privacy → Show overview`.
2. UI показывает:
   - сколько raw сообщений хранится, сколько будет удалено в ближайшие 7 дней;
   - сколько embeddings уходило в cloud за последние 30 дней (если cloud mode);
   - размер audit log.
3. Кнопки: «Wipe raw older than X», «Re-embed locally», «Run cascading export».

AC:
- Каждое действие — отдельный audit-event.

## Tokens

Документ обновляется параллельно с `tailwind.config.ts`. Здесь — итог для UX-ревью:

- Радиусы: `sm=4`, `md=8`, `lg=12`, `xl=16`.
- Spacing scale: `0.5/1/2/3/4/6/8/12/16/24` (×4px).
- Z-index: `dialog=1000`, `dropdown=900`, `tooltip=800`.
- Анимации: 150 мс default, ease-out.
- Иконки: lucide-react.

См. также `design:design-system` skill при апдейтах.
