#!/usr/bin/env bash
# F-01: delete consumer groups from transitional services after canonical cutover.
# Run only after audit confirms pending=0 and old consumers are no longer active.

set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-$(cd "$(dirname "$0")/.." && pwd)/infra/compose}"
cd "$COMPOSE_DIR"

redis_do() {
  docker compose exec -T redis sh -c "redis-cli -a \"\$REDIS_PASSWORD\" --no-auth-warning $(printf '%q ' "$@")"
}

destroy_group() {
  local stream="$1"
  local group="$2"
  local result

  result="$(redis_do XGROUP DESTROY "$stream" "$group" 2>/dev/null | tr -d '\r' || true)"
  case "$result" in
    1)
      echo "destroyed: $stream / $group"
      ;;
    0)
      echo "already absent: $stream / $group"
      ;;
    *)
      echo "warning: failed to destroy $stream / $group (result: ${result:-ERR})" >&2
      ;;
  esac
}

echo "Destroying transitional consumer groups..."
destroy_group events.telegram.message chat-summarizer
destroy_group events.telegram.message entity-extractor
destroy_group events.telegram.message task-extractor
destroy_group events.telegram.message_edited chat-summarizer
destroy_group events.telegram.message_edited task-extractor
destroy_group events.telegram.message_deleted task-extractor
destroy_group events.processing.entity_found persona-builder
echo "Done. Re-run: COMPOSE_DIR=$COMPOSE_DIR bash scripts/redis-streams-audit.sh"
