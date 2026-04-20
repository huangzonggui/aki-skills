from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "chat_orchestrator.py"
SPEC = importlib.util.spec_from_file_location("chat_orchestrator", MODULE_PATH)
chat_orchestrator = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(chat_orchestrator)


def test_parse_message_maps_core_commands() -> None:
    parsed = chat_orchestrator.parse_message("开始创作：OpenClaw 为什么要本地化")
    assert parsed.action == "start"
    assert "OpenClaw" in parsed.payload

    parsed = chat_orchestrator.parse_message("通过母稿")
    assert parsed.action == "approve_core_note"

    parsed = chat_orchestrator.parse_message("返工提示词")
    assert parsed.action == "rework"
    assert parsed.target == "prompts"


def test_append_chat_intake_writes_refs_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        topic_root = Path(tmpdir)
        (topic_root / "refs").mkdir(parents=True, exist_ok=True)

        intake = chat_orchestrator.append_chat_intake(
            topic_root=topic_root,
            channel="wechat",
            user_id="aki",
            message="补充观点：这里重点不是模型，而是工作流。",
        )

        assert intake.exists()
        text = intake.read_text(encoding="utf-8")
        assert "wechat" in text
        assert "工作流" in text


def test_handle_start_updates_session_store() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        topics_root = base / "topics"
        topics_root.mkdir()
        store = base / "sessions.json"
        topic_root = topics_root / "1. Demo-20260420-1000"

        orch = chat_orchestrator.ChatPipelineOrchestrator(
            session_store=store,
            topics_root=topics_root,
        )

        with mock.patch.object(orch, "_run_start_flow", return_value=topic_root) as start_mock:
            with mock.patch.object(orch, "_topic_status", return_value={"topic_root": str(topic_root), "current_step": "approve_core_note"}):
                result = orch.handle_message(
                    channel="wechat",
                    user_id="aki",
                    thread_id="t-1",
                    message="开始创作：OpenClaw 为什么要本地化",
                )

        start_mock.assert_called_once()
        saved = json.loads(store.read_text(encoding="utf-8"))
        assert saved["wechat:aki:t-1"]["topic_root"] == str(topic_root)
        assert result["current_step"] == "approve_core_note"


def test_handle_prompt_approval_runs_second_gate_flow() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        topics_root = base / "topics"
        topics_root.mkdir()
        store = base / "sessions.json"
        topic_root = topics_root / "1. Demo-20260420-1000"
        store.write_text(
            json.dumps({"wechat:aki:t-1": {"topic_root": str(topic_root)}}, ensure_ascii=False),
            encoding="utf-8",
        )

        orch = chat_orchestrator.ChatPipelineOrchestrator(
            session_store=store,
            topics_root=topics_root,
        )

        with mock.patch.object(orch, "_run_post_prompt_flow") as flow_mock:
            with mock.patch.object(orch, "_topic_status", return_value={"topic_root": str(topic_root), "current_step": "build_video_package"}):
                result = orch.handle_message(
                    channel="wechat",
                    user_id="aki",
                    thread_id="t-1",
                    message="通过提示词",
                )

        flow_mock.assert_called_once_with(topic_root)
        assert result["current_step"] == "build_video_package"
