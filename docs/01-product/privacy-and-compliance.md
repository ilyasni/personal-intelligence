# Приватность и compliance

PIL хранит чувствительные данные о третьих лицах. Эта страница — обязательное чтение.

## Принципы

1. **Privacy by default.** Локальный режим (только local LLM/embeddings) — дефолт. Любой исходящий трафик во внешние LLM включается явным opt-in на конкретный pipeline (entity / summarizer / memory).
2. **Self-host by default.** Канонические хранилища (Postgres, Neo4j, Qdrant, Redis) живут на Proxmox-узле пользователя. Текущее object storage для raw/media — S3 cloud.ru; целевой self-host вариант — S3-compatible object store под полным контролем владельца.
3. **Opt-in per chat.** Бот наблюдает только за чатами в allowlist. Telegram Chat Automation поддерживает это нативно; userbot — соблюдаем allowlist на уровне ingestion ДО публикации события в шину.
4. **Минимизация.** Раздельный TTL по классам данных: raw-сообщения короткий retention, derived — длинный, audit — длинный.
5. **Каскадное удаление.** На запрос «забудь X» должно удалиться всё: записи Postgres, узлы и рёбра Neo4j, payload и вектор в Qdrant, файлы object storage, упоминания в audit (с заменой на хеш для целостности журнала).
6. **Audit.** Каждое чтение через MCP логируется с указанием caller (api-key), запроса, размера ответа. Журнал хранится минимум 30 дней.

## Классы данных и ретеншен

| Класс | Где лежит | TTL по умолчанию | Можно удалить раньше | Audit-категория |
|---|---|---|---|---|
| `raw_message` (сырой текст + метаданные) | S3/object storage + zip-архивы | 90 дней | да, любым моментом | sensitive |
| `derived_person` (Person, теги, trust) | Postgres | без TTL | по запросу | sensitive |
| `derived_interaction` (Summary, sentiment) | Postgres | без TTL | по запросу | sensitive |
| `derived_task` (Task) | Postgres | до завершения + 365 дней | по запросу | sensitive |
| `graph_edge` (Neo4j рёбра/узлы) | Neo4j | без TTL | по запросу | sensitive |
| `memory_chunk` (вектор + текст) | Qdrant | 365 дней по дефолту | по запросу | sensitive |
| `audit_log` (кто что запросил) | Postgres + ELK | 365 дней | нельзя удалять, только псевдонимизация | internal |

Конкретные TTL настраиваются в Admin UI (см. [docs/06-admin-ui/ui-spec.md](../06-admin-ui/ui-spec.md)).

## Per-pipeline opt-in (cloud LLM)

В Admin UI у каждого extractor'а есть переключатель:

- `local` — только local-модель (по умолчанию);
- `cloud` — отправлять входной контекст в OpenAI/Anthropic;
- `hybrid` — отдавать только дайджесты/обезличенные фрагменты в cloud.

Внутри `libs/llm-client` есть guard, который проверяет mode и **физически** запрещает исходящий запрос, если он не разрешён.

## GDPR-подобные процедуры

Хотя PIL — self-host для одного пользователя, контакты в чатах могут попросить:

- **Право на удаление.** Реализовано через `DELETE /persons/{id}/erase` (cascading) + UI-кнопка.
- **Право на доступ.** Экспорт всего, что система знает о Person, в zip с Markdown + JSON. Endpoint `GET /persons/{id}/export`.
- **Право на ограничение обработки.** Поставить Person в blocklist — ingestion отбрасывает все события, где этот Person — отправитель/получатель/упомянут.

Все три действия логируются в audit с указанием инициатора.

## Шифрование

- Все диски Proxmox-узла шифруются на уровне LUKS (отв. оператор инсталляции).
- Секреты (Telegram session, API-ключи LLM, JWT secret) — Docker secrets или Vault (MVP-3).
- Трафик к внешним LLM — TLS 1.2+ обязательно.
- Внутренний трафик в docker-сети — plain, но порты наружу не выставляются.

## Соответствие Telegram TOS

- Уважение rate-limit'ов Telegram (Telethon встроенно).
- Запрет на массовую рассылку, скрейпинг публичных каналов вне allowlist.
- Никакого «отправлять от имени пользователя без подтверждения» — в MVP-1/2 бот строго read-only.

## Что НЕ делаем

- Не запрашиваем у Telegram больше, чем нужно (например, не хватаем медиа, если выключено в UI).
- Не отправляем embeddings в облачные сервисы без явного opt-in.
- Не сохраняем сырые сообщения дольше, чем настроено.
- Не делаем «training on user data» — никаких внешних или внутренних fine-tune без явного отдельного workflow и согласия.

## Чек-лист перед релизом

См. [docs/07-operations/runbook.md](../07-operations/runbook.md) → раздел «Privacy pre-release checklist». Минимум:

- [ ] cascading delete покрыт интеграционным тестом;
- [ ] opt-in переключатели реально гейтят исходящие запросы;
- [ ] audit log пишется на чтение MCP;
- [ ] backup создаёт зашифрованный артефакт;
- [ ] restore проверен на чистом окружении.
