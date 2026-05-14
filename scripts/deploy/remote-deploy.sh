#!/usr/bin/env bash
set -euo pipefail

REF="${1:-main}"
REPO_DIR="${REPO_DIR:-$HOME/pil}"
COMPOSE_FILE="${COMPOSE_FILE:-infra/compose/docker-compose.yml}"
ENV_FILE="${ENV_FILE:-infra/compose/.env}"
WAIT_TIMEOUT_DATA="${WAIT_TIMEOUT_DATA:-120}"
WAIT_TIMEOUT_APP="${WAIT_TIMEOUT_APP:-240}"

log() {
  printf '[deploy] %s\n' "$*"
}

compose() {
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

dump_debug() {
  local exit_code=$?
  log "deploy failed; collecting compose status"
  compose ps || true
  log "recent logs for critical services"
  compose logs --tail=120 telegram-ingestor ai-orchestrator memory-projector embedding-indexer mcp-rest-api maintenance || true
  exit "$exit_code"
}

trap dump_debug ERR

cd "$REPO_DIR"

log "updating git checkout for ref=$REF"
git fetch --prune origin
git checkout "$REF"
git pull --ff-only origin "$REF"
log "deploying commit $(git rev-parse --short HEAD)"

log "building runtime and migration images"
compose build migration-runner xray telegram-ingestor ai-orchestrator memory-projector embedding-indexer maintenance mcp-rest-api

log "bringing up datastores and waiting for health"
compose up -d --wait --wait-timeout "$WAIT_TIMEOUT_DATA" postgres redis neo4j qdrant

log "running database migrations in a containerized runner"
compose run --rm migration-runner upgrade head

log "starting application services"
compose up -d --wait --wait-timeout "$WAIT_TIMEOUT_APP" xray telegram-ingestor ai-orchestrator memory-projector embedding-indexer maintenance mcp-rest-api

log "verifying service health"
compose ps
curl -fsS http://127.0.0.1:8090/healthz >/dev/null

log "deploy completed successfully"
