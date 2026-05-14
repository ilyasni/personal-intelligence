# Prompt library

Готовые промпт-шаблоны под типовые задачи. Owner может вставлять их в любую сессию (Claude Code / Codex / Cursor) — они написаны нейтрально и опираются на общий `docs/`.

Подставь конкретные значения в `<...>` и оптом отправляй.

## Архитектурный спор / ADR

```
Я рассматриваю развилку: <короткое описание двух-трёх вариантов>.

Контекст:
- Что я строю: <раздел/сервис>.
- Какие требования это затрагивает (ссылки на docs/01-product/PRD.md и docs/02-architecture/system-overview.md).
- Что уже зафиксировано в ADR: <перечисли релевантные docs/10-adr/*>.

Задача:
1) Сделать честный pros/cons на каждый вариант (без перекоса).
2) Предложить рекомендацию с обоснованием.
3) Подготовить черновик ADR в формате docs/10-adr/0001-record-architecture-decisions.md.
4) Указать, какие тесты докажут, что выбранный вариант работает.

Не пиши код — мне нужен только ADR.
```

Лучший выбор: **Claude Code**.

## Новый pipeline-сервис

```
Создай новый сервис services/<name> по спецификации docs/05-pipelines/<name>.md.

Требования:
- Структура согласно docs/08-quality/coding-standards.md (раздел «Структура сервиса»).
- Pydantic-модели событий — из libs/contracts/.
- Consumer Redis Streams + DLQ + processed_event check.
- /healthz и /metrics.
- Unit и integration тесты.
- Запись результатов в Postgres (или Neo4j / Qdrant — см. spec).

Перед началом — прочитай:
- docs/02-architecture/components.md
- docs/03-data-model/event-schema.md
- docs/05-pipelines/<name>.md
- docs/11-agents/shared-conventions.md

В конце — handoff-блок в PR (см. docs/11-agents/handoff-protocol.md).
```

Лучший выбор: **Claude Code** (новые сервисы — сквозные).

## Миграция Postgres

```
Добавь миграцию alembic, которая <короткое описание>. Конкретика:
- Затронутые таблицы: <список>.
- Новые поля/индексы: <список>.
- Изменение типов: <если есть>.

Требования:
- Append-only (никакого редактирования прошедших миграций).
- Использовать `op.execute` для DDL, который не покрыт alembic-helpers.
- Покрыть схему snapshot-тестом (см. docs/08-quality/testing-strategy.md).
- Обновить docs/03-data-model/postgres-schema.md.

Перед началом — прочти текущий docs/03-data-model/postgres-schema.md и последние 5 миграций.

Тесты:
- `alembic upgrade head` на чистой БД должно пройти за < 60 сек.
- если миграция не обратима — добавь явный комментарий и обновь docs.
```

Лучший выбор: **Codex**.

## Cypher / Neo4j изменения

```
Добавь Cypher-миграцию migrations/neo4j/NNN_<short_name>.cypher, которая <описание>.

Требования:
- IF NOT EXISTS на constraints.
- Документация в docs/03-data-model/neo4j-graph-model.md (раздел «Constraints и индексы»).
- Идемпотентность повторного запуска.

Тесты:
- testcontainers Neo4j → запустить миграцию дважды, второй раз — без эффекта.
- если меняется операция graph-builder — обновить unit-тесты Cypher-шаблонов.
```

Лучший выбор: **Codex**.

## Покрытие тестами

```
Текущее покрытие services/<name>/src/<module>.py = <X%>. Цель — ≥ 80%.

Сгенерируй unit-тесты на непокрытые ветки. Прочитай:
- сам модуль,
- существующие тесты services/<name>/tests/unit/,
- docs/08-quality/testing-strategy.md.

Не пиши тесты под LLM-вызовы без мока. Используй фикстуры из tests/fixtures/.
```

Лучший выбор: **Codex**.

## Новый компонент Admin UI

```
Добавь экран <X> в admin-ui по docs/06-admin-ui/ux-flows.md (flow N).

Стек: React + Vite + Tailwind + TanStack Query + react-hook-form + zod.
API: docs/04-api/rest-api.md и docs/04-api/openapi.yaml.
Дизайн-токены: tailwind.config.ts и docs/06-admin-ui/ui-spec.md (раздел Tokens).
i18n: ключи в apps/admin-ui/src/i18n/{ru,en}.json.

Тесты:
- Vitest + Testing Library для компонента.
- Playwright e2e для flow.
- Aксессибилити: WCAG 2.1 AA.

Не делай UI-логику бизнес-уровня — она в backend.
```

Лучший выбор: **Cursor**.

## Расследование инцидента

```
В проде происходит <симптом>. Логи / метрики:
<вставь сюда фрагменты>

Прочитай docs/07-operations/runbook.md (особенно раздел про <симптом>) и docs/02-architecture/data-flow.md.

Задача:
1) Сформировать гипотезу о причине.
2) Указать конкретные команды/запросы для проверки.
3) Если причина воспроизводится — предложить fix как отдельный PR.
4) Постфактум — обновить runbook.

Не правь код без подтверждения от меня.
```

Лучший выбор: **Claude Code**.

## Релиз

```
Подготовь релиз vX.Y.Z.

Шаги:
1) Сгенерировать changelog из conventional commits с прошлого тэга.
2) Обновить docs/09-roadmap/milestones.md (секция «Релизы»).
3) Создать git tag.
4) Запустить .github/workflows/deploy.yml вручную.
5) После деплоя — smoke-check на текущем server runtime. Если красный — roll back.

Не меняй код — только релизные артефакты.
```

Лучший выбор: **Codex**.

## Code review (своего PR перед merge)

```
Прочитай мой PR #N и проверь:
- соответствие docs/08-quality/coding-standards.md;
- наличие handoff-блока;
- покрытие тестами;
- отсутствие нарушений docs/11-agents/shared-conventions.md;
- отсутствие новых PII в логах;
- что миграции append-only (если применимо).

Не правь — оставь комментарии.
```

Лучший выбор: **Claude Code**.

## Privacy review (раз в фазу)

```
Проверь приватность согласно docs/01-product/privacy-and-compliance.md.

Конкретно:
1) cascading delete покрыт integration-тестом и тест зелёный.
2) opt-in переключатели реально гейтят cloud LLM (e2e тест с моком сети).
3) backup создаёт зашифрованный артефакт.
4) restore drill отработан ≤ 30 дней назад.

Сделай отчёт markdown в docs/09-roadmap/milestones.md секция «Nightly results / Privacy».
```

Лучший выбор: **Claude Code**.

## Полезные общие фразы (mix-in)

- «Прежде чем писать код — прочитай <docs ссылка>».
- «Если возникнет архитектурная развилка — НЕ выбирай в одиночку, открой ADR-stub и тегни меня».
- «Тесты обязательны; без них PR не мерджу».
- «В конце — handoff-блок».
- «Обнови документацию в том же PR, что и код».
