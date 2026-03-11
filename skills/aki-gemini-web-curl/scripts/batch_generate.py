#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).with_name("gemini_web_curl.py")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch-generate Gemini Web images.")
    parser.add_argument("--items", required=True, help="JSON file containing prompt/output items")
    parser.add_argument("--chat-model", default="gemini-2.5-pro")
    parser.add_argument("--target-ratio", default="3:4")
    parser.add_argument("--reroll", type=int, default=6)
    parser.add_argument("--proxy", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    items = json.loads(Path(args.items).read_text())
    if not isinstance(items, list):
        raise SystemExit("--items must be a JSON array")

    for item in items:
        if not isinstance(item, dict):
            raise SystemExit("each batch item must be an object")
        output = item.get("output")
        prompt = item.get("prompt")
        prompt_file = item.get("prompt_file")
        if not output or not (prompt or prompt_file):
            raise SystemExit("each batch item needs output + prompt or prompt_file")

        cmd = [
            sys.executable,
            str(SCRIPT),
            "--output",
            str(output),
            "--chat-model",
            args.chat_model,
            "--target-ratio",
            args.target_ratio,
            "--reroll",
            str(args.reroll),
        ]
        if args.proxy:
            cmd.extend(["--proxy", args.proxy])
        if prompt:
            cmd.extend(["--prompt", str(prompt)])
        else:
            cmd.extend(["--prompt-file", str(prompt_file)])

        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            return proc.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
