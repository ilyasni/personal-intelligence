# Admin UI — спецификация

Web SPA для владельца инсталляции. Один пользователь, локальный self-host.

## Стек

- React 18 + Vite + TypeScript.
- Tailwind CSS (без UI-kit'ов в MVP-1, кроме небольших примитивов — `radix-ui/primitives`).
- TanStack Query — fetch/cache.
- react-router 7.
- react-hook-form + zod — формы.
- Recharts — графики (метрики, sentiment).
- i18n — react-intl, ключи в `apps/admin-ui/src/i18n/{ru,en}.json`.

## Информационная архитектура

```
/
├── /dashboard            (главная: подключения, очереди, последние tasks/persons)
├── /me                   (first-party профиль владельца)
├── /connections          (привязка ботов, allowlist чатов)
├── /persons
│   ├── /persons          (список + фильтры, только external people)
│   └── /persons/:id      (карточка)
├── /chats
│   ├── /chats            (список + allowlist)
│   └── /chats/:id        (поток interactions)
├── /tasks                (общая доска tasks)
├── /memory               (поиск + recall)
├── /audit                (audit log)
├── /system
│   ├── /health
│   ├── /queues
│   └── /jobs
├── /settings
│   ├── /general
│   ├── /privacy
│   ├── /llm
│   ├── /retention
│   └── /api-keys
└── /login
```

## Дизайн-токены

Цвет, типографика, отступы — в `apps/admin-ui/tailwind.config.ts`. Принципы:

- **Light + Dark** обязательны.
- Основной цвет — нейтральный (slate/zinc), accent — индиго.
- Шрифт — Inter (UI) + JetBrains Mono (code/JSON).
- Радиусы — `rounded-lg` дефолт, `rounded-xl` для карточек.
- Spacing — 4px grid.

Полный список — в `docs/06-admin-ui/ux-flows.md` секция «Tokens».

## Ключевые экраны

### Dashboard
- Карточка «Connections»: список (Telethon, Business Bot) со статусом.
- Карточка «Queues»: длина по основным потокам + DLQ.
- «Latest Persons»: 10 недавно обновлённых.
- «Open Tasks»: top-10.
- «Today's events»: spark line ingest/proc throughput.

### Persons list
- Поиск (q), фильтры (topic, organization).
- Owner profile здесь не показывается и открывается отдельно через `/me`.
- Колонки: avatar, display_name, role, last_interaction, trust_score, open tasks.
- Cursor pagination.

### My profile
- First-party раздел владельца инсталляции.
- Не трактуется как ordinary person card.
- Содержит:
  - стабильный owner context;
  - editable `context tags`, `preferred language`, `profile notes`;
  - рабочие/личные сегменты;
  - recent windows, в которых owner участвовал;
  - explainable note, что этот профиль влияет на анализ людей, чатов и задач.
  - в текущем server-rendered runtime хранится в канонической таблице `owner_profile`, а historical windows/tasks пока читаются через compatibility backing record.

### Person card
- Header: avatar, display_name, username, action menu (erase, export, block).
- Эта карточка применяется только к external people.
- Owner-context panel:
  - editable `relationship labels` such as `коллега`, `супруга`, `семья`, `pet-проект`;
  - free-form `relationship note`, describing how this person relates to the owner and how the AI should interpret the contact;
  - canonical persistence in `relationship_annotation`.
- Operator annotations panel:
  - editable `manual tags` for segmentation, for example `коллега`, `супруга`, `пет-проект`, `семья`, `клиент`;
  - free-form `owner note`, where владелец может оставить комментарий или контекст;
  - save action with visible last-updated timestamp and actor.
  - in the current server-rendered admin implementation, relationship labels are edited as one normalized comma-separated field and immediately become available as a people-list filter.
- Tabs:
  1. **Overview** — bio, topics, organizations, style, trust.
  2. **Interactions** — лента Interaction'ов.
  3. **Tasks** — open + закрытые (filter).
  4. **Graph** — мини-граф 1-hop (визуализация на vis.js или react-flow).
  5. **Memory** — поиск по chunks с фильтром на эту персону.
  6. **Raw** — последние сырые сообщения (если retention не вырезал).
- Кнопка «Recall…» — вызывает modal с свободным вопросом → MCP `recall_with_query`.

### Chats list / Chat detail
- Список с allowlist toggle.
- В текущем server-rendered runtime список чатов уже поддерживает owner-context filter по `relationship labels`.
- Detail содержит:
  - editable `relationship labels` для чата или канала;
  - free-form `relationship note`, описывающий как этот чат должен интерпретироваться (`работа`, `семья`, `pet-проект`, `внутренний контур`);
  - allowlist toggle;
  - последние окна и связанные задачи.
- Detail — лента Interaction'ов + кнопка «Re-summarize».

### Tasks board
- Колонки: Today, This week, Later, Done.
- Drag-to-status (опц. в MVP-2).

### Memory
- Search bar + поле «recall query».
- Слева — фильтры (type, person, topic).
- Справа — результаты с цитатой и подсветкой.

### Settings → Privacy
- Per-pipeline `local|cloud|hybrid` toggle.
- TTL для raw / memory.
- Кнопка «Export everything» (создаёт zip-job).
- Кнопка «Wipe & restart» (DEV ONLY).

### Settings → API keys
- Создание, отзыв, scopes (`read`, `mutate`).
- Показ ключа единожды.

### System → Queues
- Список потоков с длиной и lag.
- DLQ — клик → таблица событий, кнопка `retry`.

## Поведение

- **Real-time updates** — через WebSocket `/v1/stream`. Сервер пушит события `person_updated`, `task_created`, `queue_alarm`.
- **Optimistic updates** для toggle и patch-операций.
- **Empty states** — для каждой таблицы есть осмысленный empty state с CTA.
- **Errors** — RFC ProblemDetails отображается компонентом `<ErrorBanner>` со ссылкой на runbook.
- **Loading** — Suspense + skeletons.
- **Form UX for manual tags/notes** — server-rendered admin path should accept either repeated tag inputs or one normalized comma-separated field, validate through a structured form model, and always redirect after POST with explicit feedback message.

## Авторизация

- При первом запуске UI инициализирует Owner (set password / TOTP).
- JWT в HttpOnly cookie + CSRF double-submit token.
- Lockout: 5 неудачных попыток → 5 минут пауза.

## Аксессибилити

- WCAG 2.1 AA минимум.
- Keyboard navigation полностью покрыта.
- Контрастность — проверяем через `design:accessibility-review` skill.

## Тесты

- Vitest + Testing Library — компоненты + хуки.
- Playwright — e2e: вход, привязка бота, redaktor allowlist, отображение Person card, recall.
- Visual snapshot (Playwright) — ключевые экраны.

## Open questions

- Q-UI-1. Делать ли «mini-app для Telegram» в дополнение к web-UI? — see PRD Q-PRD-3.
- Q-UI-2. Поддерживать ли встроенный chat-интерфейс «спросить свою память» прямо в UI без внешнего LLM?
- Q-UI-3. Нужны ли кроме `manual tags` отдельные `relationship labels` с ограниченным словарём (`семья`, `работа`, `друзья`, `партнёр`, `хобби`) для более строгой сегментации поверх уже внедрённых free-form тегов?
