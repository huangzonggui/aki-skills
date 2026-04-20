#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
REPO_ROOT = Path(os.getenv("AKI_SKILLS_REPO_ROOT", "")).expanduser().resolve() if os.getenv("AKI_SKILLS_REPO_ROOT") else SCRIPT_DIR.parents[2]
SHARED_DIR = REPO_ROOT / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from aki_runtime import content_topics_root, default_chat_session_store  # noqa: E402
from state import invalidate_from_step, load_state  # noqa: E402
from topic_layout import resolve_layout  # noqa: E402


PIPELINE = SCRIPT_DIR / "pipeline.py"
STEP_MESSAGE_HINTS = {
    "approve_core_note": "通过母稿",
    "render_images": "通过提示词",
    "build_video_package": "状态",
    "publish_wechat_drafts": "发布公众号草稿",
}


class ParsedMessage(NamedTuple):
    action: str
    payload: str = ""
    target: str = ""


def parse_message(message: str) -> ParsedMessage:
    text = (message or "").strip()
    if not text:
        raise ValueError("message is required")

    if text.startswith("开始创作"):
        payload = re.split(r"[:：]", text, maxsplit=1)[1].strip() if re.search(r"[:：]", text) else text.replace("开始创作", "", 1).strip()
        return ParsedMessage(action="start", payload=payload)
    if text.startswith("补充来源"):
        payload = re.split(r"[:：]", text, maxsplit=1)[1].strip() if re.search(r"[:：]", text) else text.replace("补充来源", "", 1).strip()
        return ParsedMessage(action="add_source", payload=payload)
    if text.startswith("补充观点"):
        payload = re.split(r"[:：]", text, maxsplit=1)[1].strip() if re.search(r"[:：]", text) else text.replace("补充观点", "", 1).strip()
        return ParsedMessage(action="add_opinion", payload=payload)
    if text == "状态":
        return ParsedMessage(action="status")
    if text == "继续上次":
        return ParsedMessage(action="resume")
    if text == "通过母稿":
        return ParsedMessage(action="approve_core_note")
    if text == "通过提示词":
        return ParsedMessage(action="approve_prompts")
    if text.startswith("返工"):
        mapping = {
            "返工母稿": "core_note",
            "返工提示词": "prompts",
            "返工图片": "images",
            "返工视频脚本": "video_scripts",
            "返工视频": "video",
        }
        return ParsedMessage(action="rework", target=mapping.get(text, ""))
    if text == "发布公众号草稿":
        return ParsedMessage(action="publish_wechat")
    return ParsedMessage(action="add_opinion", payload=text)


def append_chat_intake(topic_root: Path, channel: str, user_id: str, message: str) -> Path:
    refs_dir = topic_root / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = refs_dir / f"chat_intake_{stamp}.md"
    body = [
        "# Chat Intake",
        "",
        f"- channel: {channel}",
        f"- user_id: {user_id}",
        f"- created_at: {stamp}",
        "",
        "## Message",
        "",
        message.strip(),
        "",
    ]
    path.write_text("\n".join(body), encoding="utf-8")
    return path


class ChatPipelineOrchestrator:
    def __init__(self, session_store: Path | None = None, topics_root: Path | None = None) -> None:
        self.session_store = (session_store or default_chat_session_store()).expanduser().resolve()
        self.topics_root = (topics_root or content_topics_root()).expanduser().resolve()

    def _session_key(self, channel: str, user_id: str, thread_id: str) -> str:
        return f"{channel}:{user_id}:{thread_id or '-'}"

    def _load_sessions(self) -> dict[str, Any]:
        if not self.session_store.exists():
            return {}
        try:
            return json.loads(self.session_store.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_sessions(self, data: dict[str, Any]) -> None:
        self.session_store.parent.mkdir(parents=True, exist_ok=True)
        self.session_store.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _run_pipeline(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(PIPELINE), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def _topic_status(self, topic_root: Path) -> dict[str, Any]:
        state = load_state(topic_root)
        current_step = None
        for step, row in state.get("steps", {}).items():
            status = row.get("status")
            if status not in {"done", "skipped"}:
                current_step = step
                break
        current_step = current_step or "complete"
        layout = resolve_layout(topic_root)
        key_paths: dict[str, str] = {}
        for label, path in {
            "topic_root": layout.root,
            "state": layout.meta_dir / "state.json",
            "core_note": layout.core_note_path,
            "core_note_draft": layout.core_note_draft_path,
            "prompt_review": layout.prompt_review_path,
            "prompts_dir": layout.prompts_dir,
            "refs_dir": layout.refs_dir,
            "video_dir": layout.video_dir,
        }.items():
            if path.exists():
                key_paths[label] = str(path)

        runtime_repo = None
        runtime_commit_sha = None
        try:
            runtime_repo = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "rev-parse", "--show-toplevel"],
                text=True,
                capture_output=True,
                check=False,
            ).stdout.strip() or str(REPO_ROOT)
            runtime_commit_sha = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
                text=True,
                capture_output=True,
                check=False,
            ).stdout.strip() or None
        except Exception:
            runtime_repo = str(REPO_ROOT)
        return {
            "topic_root": str(topic_root),
            "current_step": current_step,
            "status": state.get("status"),
            "next_action": current_step,
            "next_message": STEP_MESSAGE_HINTS.get(current_step, "状态" if current_step != "complete" else "done"),
            "key_paths": key_paths,
            "runtime_repo": runtime_repo,
            "runtime_commit_sha": runtime_commit_sha,
        }

    def _read_stdout_path(self, cp: subprocess.CompletedProcess[str]) -> Path:
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr.strip() or cp.stdout.strip() or "pipeline command failed")
        stdout = (cp.stdout or "").strip().splitlines()
        if not stdout:
            raise RuntimeError("pipeline command returned empty stdout")
        return Path(stdout[-1].strip()).expanduser().resolve()

    def _run_start_flow(self, payload: str, channel: str, user_id: str) -> Path:
        self.topics_root.mkdir(parents=True, exist_ok=True)
        title = payload.strip() or "未命名创作话题"
        init_cp = self._run_pipeline(["--intent", "init_topic", "--cwd", str(self.topics_root), "--title", title, "--mode", "prod"])
        topic_root = self._read_stdout_path(init_cp)
        intake = append_chat_intake(topic_root, channel, user_id, payload or title)
        ingest_cp = self._run_pipeline(["--intent", "ingest_sources", "--topic-root", str(topic_root), "--source", str(intake)])
        if ingest_cp.returncode != 0:
            raise RuntimeError(ingest_cp.stderr.strip() or ingest_cp.stdout.strip() or "ingest_sources failed")
        summarize_cp = self._run_pipeline(["--intent", "summarize_core_note", "--topic-root", str(topic_root)])
        if summarize_cp.returncode != 0:
            raise RuntimeError(summarize_cp.stderr.strip() or summarize_cp.stdout.strip() or "summarize_core_note failed")
        co_create_cp = self._run_pipeline(["--intent", "co_create_core_note", "--topic-root", str(topic_root)])
        if co_create_cp.returncode != 0:
            raise RuntimeError(co_create_cp.stderr.strip() or co_create_cp.stdout.strip() or "co_create_core_note failed")
        return topic_root

    def _run_ingest_refresh_flow(self, topic_root: Path, payload: str, channel: str, user_id: str) -> None:
        intake = append_chat_intake(topic_root, channel, user_id, payload)
        ingest_cp = self._run_pipeline(["--intent", "ingest_sources", "--topic-root", str(topic_root), "--source", str(intake)])
        if ingest_cp.returncode != 0:
            raise RuntimeError(ingest_cp.stderr.strip() or ingest_cp.stdout.strip() or "ingest_sources failed")
        invalidate_from_step(topic_root, "summarize_core_note", reason="new chat intake added")
        summarize_cp = self._run_pipeline(["--intent", "summarize_core_note", "--topic-root", str(topic_root)])
        if summarize_cp.returncode != 0:
            raise RuntimeError(summarize_cp.stderr.strip() or summarize_cp.stdout.strip() or "summarize_core_note failed")

    def _run_core_note_approval_flow(self, topic_root: Path) -> None:
        for intent in ("approve_core_note", "derive_platform_copies", "generate_prompts"):
            cp = self._run_pipeline(["--intent", intent, "--topic-root", str(topic_root)])
            if cp.returncode != 0:
                raise RuntimeError(cp.stderr.strip() or cp.stdout.strip() or f"{intent} failed")

    def _run_post_prompt_flow(self, topic_root: Path) -> None:
        render_cp = self._run_pipeline(
            ["--intent", "render_images", "--topic-root", str(topic_root), "--approved-prompt-titles"]
        )
        if render_cp.returncode != 0:
            raise RuntimeError(render_cp.stderr.strip() or render_cp.stdout.strip() or "render_images failed")
        for intent in ("derive_video_scripts", "build_video_package"):
            args = ["--intent", intent, "--topic-root", str(topic_root)]
            if intent == "build_video_package":
                args.append("--force-export")
            cp = self._run_pipeline(args)
            if cp.returncode != 0:
                raise RuntimeError(cp.stderr.strip() or cp.stdout.strip() or f"{intent} failed")

    def handle_message(self, channel: str, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        parsed = parse_message(message)
        sessions = self._load_sessions()
        key = self._session_key(channel, user_id, thread_id)
        topic_root_raw = ((sessions.get(key) or {}).get("topic_root") or "").strip()
        topic_root = Path(topic_root_raw).expanduser() if topic_root_raw else None

        if parsed.action == "start":
            topic_root = self._run_start_flow(parsed.payload, channel, user_id)
            sessions[key] = {"topic_root": str(topic_root)}
            self._save_sessions(sessions)
            return self._topic_status(topic_root)

        if topic_root is None:
            raise RuntimeError("No active topic for this session. 请先发送“开始创作：...”")

        if parsed.action in {"add_source", "add_opinion"}:
            self._run_ingest_refresh_flow(topic_root, parsed.payload, channel, user_id)
            return self._topic_status(topic_root)
        if parsed.action == "status":
            return self._topic_status(topic_root)
        if parsed.action == "resume":
            return self._topic_status(topic_root)
        if parsed.action == "approve_core_note":
            self._run_core_note_approval_flow(topic_root)
            return self._topic_status(topic_root)
        if parsed.action == "approve_prompts":
            self._run_post_prompt_flow(topic_root)
            return self._topic_status(topic_root)
        if parsed.action == "rework":
            if not parsed.target:
                raise RuntimeError("Unknown rework target")
            cp = self._run_pipeline(["--intent", "rework", "--topic-root", str(topic_root), "--target", parsed.target])
            if cp.returncode != 0:
                raise RuntimeError(cp.stderr.strip() or cp.stdout.strip() or "rework failed")
            return self._topic_status(topic_root)
        if parsed.action == "publish_wechat":
            cp = self._run_pipeline(["--intent", "publish_wechat_drafts", "--topic-root", str(topic_root)])
            if cp.returncode != 0:
                raise RuntimeError(cp.stderr.strip() or cp.stdout.strip() or "publish_wechat_drafts failed")
            return self._topic_status(topic_root)

        raise RuntimeError(f"Unsupported action: {parsed.action}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Chat entrypoint for aki-content-pipeline-pro")
    parser.add_argument("--channel", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--thread-id", default="-")
    parser.add_argument("--message", required=True)
    parser.add_argument("--session-store", default="")
    parser.add_argument("--topics-root", default="")
    args = parser.parse_args()

    orch = ChatPipelineOrchestrator(
        session_store=Path(args.session_store).expanduser() if args.session_store else None,
        topics_root=Path(args.topics_root).expanduser() if args.topics_root else None,
    )
    result = orch.handle_message(
        channel=args.channel,
        user_id=args.user_id,
        thread_id=args.thread_id,
        message=args.message,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
