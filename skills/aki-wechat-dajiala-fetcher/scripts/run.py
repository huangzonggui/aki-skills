#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path("/Users/aki/Downloads/Browsers/自媒体")
ENV_FILES = (SKILL_DIR / ".env",)


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            os.environ.setdefault(key, value)


def ensure_output_arg(args: list[str]) -> list[str]:
    for arg in args:
        if arg == "--output" or arg.startswith("--output="):
            return args
    return args + ["--output", str(DEFAULT_OUTPUT)]


def main() -> int:
    for env_file in ENV_FILES:
        load_env(env_file)

    script_path = Path(__file__).with_name("wechat_agent.py")
    if not script_path.exists():
        print(f"wechat_agent.py not found at {script_path}", file=sys.stderr)
        return 1

    args = ensure_output_arg(sys.argv[1:])
    cmd = [sys.executable, str(script_path), *args]
    return subprocess.call(cmd, cwd=str(SKILL_DIR))


if __name__ == "__main__":
    raise SystemExit(main())
