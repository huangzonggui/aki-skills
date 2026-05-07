#!/usr/bin/env bash
set -euo pipefail
echo "=== Aki Content Pipeline Pro Setup ==="

python3 --version || { echo "[FAIL] Python 3.10+ required"; exit 1; }

if [ -z "${AKI_SKILLS_REPO_ROOT:-}" ]; then
    export AKI_SKILLS_REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
fi

if python3 -c "from PIL import Image" 2>/dev/null; then
    echo "[OK] Pillow installed"
else
    echo "Installing Pillow..."
    pip3 install Pillow
fi

if [ -f ~/.config/ai/keys.env ]; then
    echo "[OK] Config found: ~/.config/ai/keys.env"
else
    echo "[WARN] Copy config/keys.env.example to ~/.config/ai/keys.env"
fi

if command -v ffmpeg &>/dev/null; then
    echo "[OK] ffmpeg available (full pipeline)"
else
    echo "[INFO] ffmpeg not found (video only, optional)"
fi

echo "Setup complete. Run: python3 scripts/check_env.py"
