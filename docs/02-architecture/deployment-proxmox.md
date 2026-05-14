# Deployment: Proxmox + Docker Compose

PIL разрабатывается и эксплуатируется на домашнем сервере Proxmox VE. Ниже разделены:

- **текущее состояние** на 2026-05-12;
- **целевое состояние** для MVP-1/2, когда runtime и data-plane будут разведены аккуратнее.

MVP-3 опционально мигрирует на k3s.

## Текущее состояние

- Одна VM `personal-intelligence` (`192.168.31.165`), Debian 13.
- Рабочая директория runtime: `~/pil`.
- Подняты `postgres`, `redis`, `neo4j`, `qdrant`, `xray`, `telegram-ingestor`, `entity-extractor`, `persona-builder`.
- Raw storage вынесен в S3 cloud.ru; локального MinIO в текущем compose нет.
- `mcp-rest-api`, `admin-ui`, `maintenance`, `prometheus/grafana/loki` пока описываются как следующий этап.

## Топология

```
┌──────────────────────────────────────────────────┐
│              Proxmox host (bare metal)            │
│  ┌────────────────────┐  ┌─────────────────────┐  │
│  │  VM "pil-dev"      │  │ VM "pil-data"       │  │
│  │  (Debian 12)       │  │ (Debian 12)         │  │
│  │  Docker Compose:   │  │ Docker Compose:     │  │
│  │  - ingestor        │  │ - postgres          │  │
│  │  - extractors      │  │ - neo4j             │  │
│  │  - api             │  │ - qdrant            │  │
│  │  - admin-ui        │  │ - minio             │  │
│  │  - prometheus      │  │ - redis             │  │
│  │  - grafana         │  │                     │  │
│  └────────────────────┘  └─────────────────────┘  │
│         ↑ tailscale / private bridge ↑            │
└──────────────────────────────────────────────────┘
```

### Почему две VM

- **pil-data** — состояние. Снапшоты Proxmox раз в сутки, бэкап LUKS-зашифрованного диска на NAS. Перезагрузка редкая.
- **pil-dev** — компьюты. Перезаливаются часто, без боли. Можно держать дублирующую `pil-prod` рядом.

Это остаётся **целевой схемой**. Фактически MVP сейчас работает на одной VM и одном `docker-compose.yml`.

### Рекомендуемые ресурсы (минимум)

| VM        | vCPU | RAM   | Диск             |
|-----------|------|-------|------------------|
| pil-dev   | 4    | 8 GB  | 60 GB SSD        |
| pil-data  | 4    | 16 GB | 200 GB SSD (для Postgres+Qdrant) + 500 GB HDD (object storage/backups) |

## Сетевые порты (внутренние)

| Сервис     | Внутр. порт | Откуда доступен               |
|------------|-------------|-------------------------------|
| postgres   | 5432        | pil-dev only                  |
| neo4j      | 7687, 7474  | pil-dev only                  |
| qdrant     | 6333, 6334  | pil-dev only                  |
| minio      | 9000, 9001  | pil-dev + Admin UI            |
| redis      | 6379        | pil-dev only                  |
| api        | 8080        | reverse-proxy (Caddy)         |
| admin-ui   | 5173 (dev), 80 (prod) | reverse-proxy        |
| grafana    | 3000        | reverse-proxy (auth)          |

Наружу торчит только Caddy на 443. TLS — Let's Encrypt с DNS-challenge (для домашнего домена через Cloudflare).

## Шаги развёртывания

1. **Подготовить Proxmox.**
   - LUKS на дисках, ZFS/LVM-thin для VM.
   - Сетевой bridge `vmbr1` для приватной сети между VM.
2. **Создать VM.**
   - Debian 12 cloud-init или ручная установка.
   - SSH key only, отключить пароль.
   - tailscale / wireguard для удалённого доступа.
3. **Поднять Docker и compose.**
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-v2 make git
   sudo usermod -aG docker $USER
   ```
4. **Склонировать репо.**
   ```bash
   git clone <repo> personal-intelligence && cd personal-intelligence
   cp .env.example .env
   # заполнить TELETHON_API_ID, TELETHON_API_HASH, BOT_TOKEN (опц.), JWT_SECRET, и т.д.
   ```
5. **Запустить.**
   ```bash
   make up               # полный checkout, целевой workflow
   make deps             # полный checkout, только зависимости
   make migrate          # полный checkout, миграции
   ```
6. **Привязать бота.**
   - Создать бота в @BotFather, включить ему Business Mode (`/setbusinessmode`).
   - В Admin UI указать BOT_TOKEN.
   - В Telegram: Settings → Chat Automation → выбрать бота.
   - Альтернатива: запустить Telethon userbot, авторизоваться через QR-код в Admin UI.
7. **Настроить allowlist.** Admin UI → Chats → отметить нужные.
8. **Проверить smoke.** В текущем `Makefile` `make smoke` показывает healthchecks контейнеров. Для фактической проверки pipeline дополнительно отправить тестовое сообщение и проверить логи `telegram-ingestor`, `entity-extractor`, `persona-builder`.

## Бэкапы

- Proxmox-снапшоты VM раз в сутки (vzdump, на NAS).
- Логические бэкапы из `services/maintenance` тоже раз в сутки в backup/object storage (см. [docs/07-operations/backups-and-retention.md](../07-operations/backups-and-retention.md)).
- Два уровня независимы — это сделано осознанно.

## Обновления

- Целевой flow: ветка → PR → CI → merge → обновление server runtime.
- Текущий flow: синхронизация runtime-дерева в `~/pil`, затем `docker compose ... up -d` и ручной `alembic upgrade head`.
- Для data-plane миграции всё ещё применяются вручную и без `snapshot-all` wrapper'а.

## Безопасность

- Все секреты — Docker secrets (compose) или файл `.env` с правами `chmod 600`.
- Внешние порты — только 443 на Caddy.
- Audit log при чтении MCP пишется всегда.
- Owner-аккаунт защищён 2FA (TOTP) поверх JWT.

## Что в MVP-3 (опц. k3s)

- Заменить compose на k3s + helm.
- Statefulset для postgres/neo4j/qdrant с PVC.
- Ingress-nginx + cert-manager.
- Vault для секретов.
- Multi-account через namespace-per-tenant.
