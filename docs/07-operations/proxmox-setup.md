# Proxmox setup

Конкретная инструкция для домашнего Proxmox VE (на время разработки).

## Хост

- Proxmox VE 8.x, kernel 6.17.13-1-pve.
- VM `personal-intelligence` (VM 105): Debian 13 (trixie), 4 vCPU, 8 GB RAM, 118 GB disk.
- IP: `192.168.31.165` (LAN).

## Подключение к серверу

```bash
# Основной пользователь разработки (SSH ключ)
ssh ilyasni@192.168.31.165

# Рут (только для экстренного доступа)
ssh root@192.168.31.165
```

SSH-ключ (добавлен в `~/.ssh/authorized_keys` для `ilyasni`):
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEB3pjcbkA1lJ46/CJgokEFaJrX3adkyIUYRka6sQrjO promo.sni@gmail.com
```

Для добавления ключа на новой машине:
```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub ilyasni@192.168.31.165
```

## Что установлено

| Пакет | Версия |
|-------|--------|
| OS | Debian 13 (trixie) |
| Docker Engine | 29.4.3 |
| Docker Compose | v5.1.3 (плагин) |
| Python | 3.13 |
| Git | 2.47.3 |
| Make, jq, htop, tmux | latest |

Docker настроен:
- `systemctl enable docker` — автозапуск при ребуте.
- `ilyasni` в группе `docker` — команды без `sudo`.
- Ротация логов: `max-size: 10m`, `max-file: 3`.
- daemon.json: `172.20.0.0/14` address pool.

## Расположение проекта на сервере

```
/home/ilyasni/
└── pil/
    ├── infra/compose/          # docker-compose.yml, .env, secrets/
    ├── libs/
    ├── migrations/
    └── services/
```

Важно:

- это **server truth checkout** с настроенным `origin` на `github-personal-intelligence:ilyasni/personal-intelligence.git`;
- `docs/` и `scripts/` хранятся в том же checkout и обновляются вместе с runtime-кодом;
- корневой `Makefile` и compose/smoke tooling уже должны присутствовать в актуальном runtime-дереве;
- локальная planning-копия остаётся удобной рабочей средой, но deploy/source-of-truth теперь живёт на сервере в `~/pil`.

## Стек сервисов (deps)

Поднимается через `make deps` из `infra/compose/`:

| Сервис | Порт (localhost) | Описание |
|--------|-----------------|----------|
| PostgreSQL 16 | 5432 | Основная RDBMS |
| Redis 7.2 | 6379 | Message bus (Streams) |
| Neo4j 5 Community | 7474 (HTTP), 7687 (Bolt) | Graph DB |
| Qdrant v1.10 | 6333 (REST), 6334 (gRPC) | Vector DB |
| S3 cloud.ru | внешний endpoint | Object store для raw/media |

Все порты слушают только на `127.0.0.1` сервера — не доступны извне напрямую.

## Обновление / деплой

```bash
ssh ilyasni@192.168.31.165
cd ~/pil

# preferred: GitHub Actions workflow_dispatch -> Deploy
# fallback from server shell:
bash scripts/deploy/remote-deploy.sh main
```

Если нужен ручной rollout из checkout без GitHub Actions:

```bash
make deploy-runtime
```

`deploy-runtime` сам выполнит build, поднимет data-layer через `docker compose up -d --wait`, прогонит `migration-runner`, затем поднимет app-layer и завершит всё через `make smoke-strict`.

## Snapshots и backup

- Proxmox snapshots: ежесуточно в 03:00, retention 7.
- Автоматизированный логический backup-контур ещё собирается; см. backups-and-retention.md.

## Безопасность

- SSH только по ключу (`PasswordAuthentication no` рекомендуется).
- `ilyasni` — `NOPASSWD:ALL` sudo (dev-режим, ограничить в prod).
- Секреты в `infra/compose/.env` (`chmod 600`), не в репо.
- Docker daemon не слушает TCP (только unix socket).

## Восстановление после сбоя

Если VM умерла:
1. Восстановить из Proxmox-снапшота.
2. Вернуть актуальное runtime-дерево в `~/pil` и проверить наличие `infra/compose/.env`.
3. `make deploy-runtime`.
4. При canonical cutover дополнительно прогнать `make cutover-audit`.
