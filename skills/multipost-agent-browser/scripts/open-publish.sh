#!/usr/bin/env bash
set -euo pipefail

SESSION="${1:-multipost}"
STATE_FILE="${2:-$HOME/.cache/agent-browser/multipost-state.json}"
PUBLISH_URL="${3:-https://multipost.app/dashboard/publish}"

if [[ -f "$STATE_FILE" ]]; then
  echo "[multipost] Loading auth state: $STATE_FILE"
  agent-browser --session "$SESSION" state load "$STATE_FILE"
else
  echo "[multipost] No auth state file found at: $STATE_FILE"
  echo "[multipost] Run scripts/bootstrap-session.sh first if login is required."
fi

echo "[multipost] Opening publish page..."
agent-browser --session "$SESSION" --headed open "$PUBLISH_URL"
agent-browser --session "$SESSION" wait --load networkidle
agent-browser --session "$SESSION" snapshot -i -c
