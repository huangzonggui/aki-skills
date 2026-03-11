#!/usr/bin/env bash
set -euo pipefail

runtime_dir="/home/aki/openclaw-obsidian-brain"
script_path="$runtime_dir/brain_router.py"
config_path="$runtime_dir/config.json"

if [[ ! -f "$script_path" ]]; then
  echo "brain router not found: $script_path" >&2
  exit 1
fi

if [[ ! -f "$config_path" ]]; then
  echo "brain router config not found: $config_path" >&2
  exit 1
fi

exec runuser -u aki -- python3 "$script_path" --config "$config_path" "$@"
