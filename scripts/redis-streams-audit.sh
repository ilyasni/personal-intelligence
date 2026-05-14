#!/usr/bin/env bash
# Audit Redis Streams for F-01 cutover: lengths and consumer groups.
# Keep the STREAMS list in sync with libs/contracts events and commands.

set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-$(cd "$(dirname "$0")/.." && pwd)/infra/compose}"
cd "$COMPOSE_DIR"

STREAMS=(
  "events.telegram.message"
  "events.telegram.message_edited"
  "events.telegram.message_deleted"
  "events.telegram.chat_member"
  "events.telegram.business_connection"
  "events.telegram.preprocessed"
  "events.processing.entity_found"
  "events.dlq.entity_found"
  "events.processing.person_updated"
  "events.processing.task_created"
  "events.processing.task_resolved"
  "events.processing.interaction_updated"
  "events.dlq.task_extractor"
  "events.dlq.chat_summarizer"
  "events.ai.analysis_completed"
  "events.ai.analytics_signal"
  "events.ai.projection_command"
  "events.ai.embedding_requested"
  "events.ai.reprocess_window"
  "system.command"
)

redis_do() {
  docker compose exec -T redis sh -c "redis-cli -a \"\$REDIS_PASSWORD\" --no-auth-warning $(printf '%q ' "$@")"
}

echo "=== Redis streams audit (compose: $COMPOSE_DIR) ==="
for stream in "${STREAMS[@]}"; do
  exists="$(redis_do EXISTS "$stream" 2>/dev/null | tr -d '\r' || echo ERR)"
  if [[ "$exists" != "1" ]]; then
    echo "- $stream (missing key, EXISTS=$exists)"
    continue
  fi

  length="$(redis_do XLEN "$stream" 2>/dev/null | tr -d '\r')"
  echo "+ $stream XLEN=$length"
  redis_do XINFO GROUPS "$stream" 2>/dev/null | tr -d '\r' | sed 's/^/    /' || echo "    (XINFO GROUPS error)"
  echo ""
done
echo "=== done ==="
