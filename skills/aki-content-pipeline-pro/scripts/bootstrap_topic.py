#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from state import DONE, load_state, save_state, set_step
from topic_layout import resolve_layout
from utils import find_min_prefix, sanitize_title, ts_label


def build_topic_dir_name(base_dir: Path, title: str, timestamp: str) -> str:
    prefix = find_min_prefix(base_dir)
    safe_title = sanitize_title(title)
    return f"{prefix}. {safe_title}-{timestamp}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a topic root directory for aki-content-pipeline-pro")
    parser.add_argument("--cwd", default=".", help="Base directory")
    parser.add_argument("--title", required=True, help="Explosive topic title")
    parser.add_argument("--mode", choices=["prod", "test"], default="prod")
    parser.add_argument("--timestamp", default="", help="Override timestamp label YYYYMMDD-HHMM")
    args = parser.parse_args()

    base_dir = Path(args.cwd).expanduser().resolve()
    stamp = args.timestamp.strip() or ts_label()
    folder_name = build_topic_dir_name(base_dir, args.title, stamp)
    topic_root = base_dir / folder_name
    suffix = 2
    while topic_root.exists():
        topic_root = base_dir / f"{folder_name}-r{suffix:02d}"
        suffix += 1

    topic_root.mkdir(parents=True, exist_ok=False)
    layout = resolve_layout(topic_root)
    layout.ensure_structure()

    topic_meta = {
        "title": args.title.strip(),
        "mode": args.mode,
        "topic_root": str(topic_root),
        "created_at": stamp,
    }
    layout.topic_meta_path.write_text(
        json.dumps(topic_meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    state = load_state(topic_root, mode=args.mode)
    state["mode"] = args.mode
    save_state(topic_root, state)
    set_step(topic_root, "init_topic", DONE, message="Topic directory initialized", meta=topic_meta)

    print(str(topic_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
