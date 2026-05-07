#!/usr/bin/env python3
"""Check environment readiness for aki-content-pipeline-pro."""
import os, shutil, sys
from pathlib import Path

def ok(msg): print(f"  [OK] {msg}")
def warn(msg): print(f"  [WARN] {msg}")
def fail(msg): print(f"  [FAIL] {msg}")

errors = 0

print("=== Python ===")
ver = sys.version_info
if ver >= (3, 10):
    ok(f"Python {ver.major}.{ver.minor}.{ver.micro}")
else:
    fail(f"Python {ver.major}.{ver.minor} (need 3.10+)")
    errors += 1

print("\n=== API Keys ===")
key_file = Path.home() / ".config" / "ai" / "keys.env"
comfly_key = os.getenv("COMFLY_API_KEY", "")
if not comfly_key and key_file.exists():
    for line in key_file.read_text().splitlines():
        if line.startswith("COMFLY_API_KEY="):
            comfly_key = line.split("=", 1)[1].strip().strip("'\"")
            break
if comfly_key and comfly_key != "sk-your-key-here":
    ok(f"COMFLY_API_KEY found ({len(comfly_key)} chars)")
else:
    fail("COMFLY_API_KEY not set. Copy config/keys.env.example to ~/.config/ai/keys.env")
    errors += 1

print("\n=== Image Processing ===")
try:
    from PIL import Image
    ok("Pillow installed (cross-platform image support)")
except ImportError:
    if sys.platform == "darwin":
        warn("Pillow not installed. Falling back to macOS sips. pip install Pillow recommended.")
    else:
        fail("Pillow not installed. REQUIRED on Windows/Linux. Run: pip install Pillow")
        errors += 1

print("\n=== Optional: Video (full pipeline) ===")
if shutil.which("ffmpeg"):
    ok("ffmpeg available")
else:
    warn("ffmpeg not found (required for video export only)")

print(f"\n=== Summary: {errors} error(s) ===")
sys.exit(1 if errors else 0)
