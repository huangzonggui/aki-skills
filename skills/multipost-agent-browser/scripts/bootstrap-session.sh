#!/usr/bin/env bash
set -euo pipefail

SESSION="${1:-multipost}"
STATE_FILE="${2:-$HOME/.cache/agent-browser/multipost-state.json}"

mkdir -p "$(dirname "$STATE_FILE")"

echo "[multipost] Open sign-in page in headed mode..."
agent-browser --session "$SESSION" --headed open https://multipost.app/signin

echo "[multipost] Please complete login in browser, then press Enter to save auth state."
read -r _

agent-browser --session "$SESSION" state save "$STATE_FILE"
echo "[multipost] Saved auth state: $STATE_FILE"
