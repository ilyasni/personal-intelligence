COMPOSE_DIR := infra/compose
COMPOSE     := docker compose -f $(COMPOSE_DIR)/docker-compose.yml --env-file $(COMPOSE_DIR)/.env
CANONICAL_PY_DIRS := libs/contracts libs/llm-client libs/observability libs/storage-clients \
	services/telegram-ingestor services/ai-orchestrator services/memory-projector \
	services/embedding-indexer services/mcp-rest-api services/maintenance

.PHONY: help deps up down logs ps smoke smoke-wait smoke-strict cutover-audit cutover-cleanup \
        verify lint lint-runtime fmt typecheck typecheck-runtime install install-dev pre-commit-install nuke

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo "PIL project targets:"
	@echo ""
	@echo "  Infrastructure:"
	@echo "    deps        — поднять хранилища (postgres, redis, neo4j, qdrant)"
	@echo "    up          — весь стек"
	@echo "    down        — остановить всё"
	@echo "    logs        — tail логов"
	@echo "    ps          — статус контейнеров"
	@echo "    smoke       — таблица статусов контейнеров"
	@echo "    smoke-wait  — up -d --wait (дождаться healthy/running, до 120 с)"
	@echo "    smoke-strict — smoke + нет unhealthy + curl /healthz mcp-rest-api"
	@echo "    nuke        — DEV ONLY: down + удалить все volumes"
	@echo ""
	@echo "  Development:"
	@echo "    install     — установить все зависимости (все libs + services)"
	@echo "    install-dev — установить dev-зависимости (ruff, mypy, pytest)"
	@echo "    lint        — ruff check"
	@echo "    lint-runtime — ruff check по canonical runtime"
	@echo "    fmt         — ruff format"
	@echo "    typecheck   — mypy"
	@echo "    verify      — lint + typecheck + test"
	@echo "    pre-commit-install — установить pre-commit хуки"

# ── Infrastructure ────────────────────────────────────────────────────────────
deps:
	$(COMPOSE) up -d postgres redis neo4j qdrant

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

smoke:
	@echo "=== Healthchecks ==="
	@$(COMPOSE) ps --format "table {{.Name}}\t{{.Status}}"

# После деплоя: дождаться готовности стека (см. docker compose up --wait в доке Compose).
smoke-wait:
	$(COMPOSE) up -d --wait --wait-timeout 120

# F-01 / cutover: падает, если есть unhealthy или недоступен API health (127.0.0.1:8090).
smoke-strict: smoke
	@echo "=== Strict: no unhealthy containers ==="
	@if $(COMPOSE) ps 2>/dev/null | grep -qi unhealthy; then echo "FAIL: unhealthy container(s)"; exit 1; fi
	@echo "=== mcp-rest-api GET /healthz ==="
	@curl -sf http://127.0.0.1:8090/healthz >/dev/null && echo OK || (echo "FAIL: mcp-rest-api /healthz"; exit 1)

cutover-audit:
	bash scripts/redis-streams-audit.sh

cutover-cleanup:
	bash scripts/redis-orphan-groups-cutover.sh

nuke:
	@echo "WARNING: This will delete all data volumes!"
	@read -p "Are you sure? [y/N] " c && [ "$$c" = "y" ]
	$(COMPOSE) down -v

# ── Development ───────────────────────────────────────────────────────────────
install:
	pip install -e libs/contracts -e libs/observability -e libs/storage-clients -e libs/llm-client
	pip install -e services/telegram-ingestor
	pip install -e services/ai-orchestrator
	pip install -e services/chat-summarizer
	pip install -e services/memory-projector
	pip install -e services/embedding-indexer
	pip install -e services/mcp-rest-api
	pip install -e services/maintenance
	pip install -e services/task-extractor

install-dev:
	pip install ruff mypy pytest pytest-asyncio pydantic-settings alembic psycopg2-binary

migrate:
	POSTGRES_DSN=postgresql+psycopg2://pil:$(shell grep POSTGRES_PASSWORD $(COMPOSE_DIR)/.env | cut -d= -f2)@localhost:5432/pil \
	  alembic -c migrations/alembic.ini upgrade head

migrate-status:
	POSTGRES_DSN=postgresql+psycopg2://pil:$(shell grep POSTGRES_PASSWORD $(COMPOSE_DIR)/.env | cut -d= -f2)@localhost:5432/pil \
	  alembic -c migrations/alembic.ini current

lint:
	ruff check libs/ services/

lint-runtime:
	ruff check $(CANONICAL_PY_DIRS)

fmt:
	ruff format libs/ services/

typecheck:
	mypy libs/ services/ --config-file pyproject.toml

typecheck-runtime:
	mypy $(CANONICAL_PY_DIRS) --config-file pyproject.toml

test:
	pytest tests/ -v

verify: lint-runtime typecheck-runtime test

pre-commit-install:
	pre-commit install
