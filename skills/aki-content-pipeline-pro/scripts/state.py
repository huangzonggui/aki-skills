#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STEP_ORDER = [
    "init_topic",
    "ingest_sources",
    "summarize_core_note",
    "approve_core_note",
    "derive_platform_copies",
    "generate_prompts",
    "render_images",
    "derive_video_scripts",
    "build_video_package",
    "publish_wechat_drafts",
]

PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
BLOCKED = "blocked"
SKIPPED = "skipped"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_path(topic_root: Path) -> Path:
    return topic_root / "meta" / "state.json"


def _empty_step() -> dict[str, Any]:
    return {"status": PENDING, "updated_at": now_iso(), "message": "", "meta": {}}


def _default_state(topic_root: Path, mode: str) -> dict[str, Any]:
    return {
        "topic_root": str(topic_root.resolve()),
        "mode": mode,
        "status": PENDING,
        "updated_at": now_iso(),
        "steps": {step: _empty_step() for step in STEP_ORDER},
        "artifacts": {},
        "history": [],
    }


def load_state(topic_root: Path, mode: str | None = None) -> dict[str, Any]:
    path = state_path(topic_root)
    if not path.exists():
        data = _default_state(topic_root, mode or "prod")
        save_state(topic_root, data)
        return data
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("steps", {})
    for step in STEP_ORDER:
        data["steps"].setdefault(step, _empty_step())
        data["steps"][step].setdefault("status", PENDING)
        data["steps"][step].setdefault("updated_at", now_iso())
        data["steps"][step].setdefault("message", "")
        data["steps"][step].setdefault("meta", {})
    data.setdefault("artifacts", {})
    data.setdefault("history", [])
    data.setdefault("status", PENDING)
    data.setdefault("mode", mode or "prod")
    data.setdefault("updated_at", now_iso())
    return data


def save_state(topic_root: Path, state: dict[str, Any]) -> None:
    path = state_path(topic_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now_iso()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _recompute_status(state: dict[str, Any]) -> str:
    statuses = [row.get("status", PENDING) for row in state.get("steps", {}).values()]
    if any(status == FAILED for status in statuses):
        return FAILED
    if any(status == BLOCKED for status in statuses):
        return BLOCKED
    if statuses and all(status in {DONE, SKIPPED} for status in statuses):
        return DONE
    if any(status in {RUNNING, DONE, BLOCKED, SKIPPED} for status in statuses):
        return RUNNING
    return PENDING


def set_step(
    topic_root: Path,
    step: str,
    status: str,
    message: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = load_state(topic_root)
    if step not in state["steps"]:
        raise KeyError(f"Unknown step: {step}")
    row = state["steps"][step]
    row["status"] = status
    row["updated_at"] = now_iso()
    if message:
        row["message"] = message
    if meta is not None:
        row["meta"] = meta
    state["history"].append(
        {"time": now_iso(), "step": step, "status": status, "message": message, "meta": meta or {}}
    )
    state["status"] = _recompute_status(state)
    save_state(topic_root, state)
    return state


def set_artifact(topic_root: Path, key: str, value: Any) -> dict[str, Any]:
    state = load_state(topic_root)
    state["artifacts"][key] = value
    save_state(topic_root, state)
    return state


def invalidate_from_step(topic_root: Path, step: str, reason: str) -> dict[str, Any]:
    state = load_state(topic_root)
    if step not in STEP_ORDER:
        raise KeyError(f"Unknown step: {step}")
    start = STEP_ORDER.index(step)
    for name in STEP_ORDER[start:]:
        state["steps"][name]["status"] = PENDING
        state["steps"][name]["message"] = f"invalidated: {reason}"
        state["steps"][name]["updated_at"] = now_iso()
        state["steps"][name]["meta"] = {}
    state["history"].append(
        {"time": now_iso(), "step": step, "status": "invalidated", "message": reason, "meta": {}}
    )
    state["status"] = _recompute_status(state)
    save_state(topic_root, state)
    return state


def first_incomplete_step(state: dict[str, Any]) -> str | None:
    for step in STEP_ORDER:
        status = state["steps"].get(step, {}).get("status", PENDING)
        if status not in {DONE, SKIPPED}:
            return step
    return None


def step_done(topic_root: Path, step: str) -> bool:
    state = load_state(topic_root)
    return state["steps"][step]["status"] == DONE
