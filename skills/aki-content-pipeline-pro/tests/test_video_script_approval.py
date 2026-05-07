from __future__ import annotations

import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import pipeline  # noqa: E402
from state import DONE, load_state, set_step  # noqa: E402
from topic_layout import resolve_layout  # noqa: E402


class VideoScriptApprovalTests(unittest.TestCase):
    def test_allocate_video_segment_durations_defaults_to_about_30_seconds(self) -> None:
        cover_sec, page_durations = pipeline._allocate_video_segment_durations(3)

        self.assertEqual(cover_sec, 4.0)
        self.assertEqual(len(page_durations), 3)
        self.assertAlmostEqual(cover_sec + sum(page_durations), 30.0, places=1)

    def test_video_script_approval_is_invalidated_after_script_edit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            layout = resolve_layout(root)
            layout.ensure_structure()

            voice_path = layout.video_voice_script_path("wechat")
            tts_path = layout.video_voice_tts_script_path("wechat")
            voice_path.write_text("# wechat_video 口播脚本\n\n## 01. cover_01\n\n这是第一版视频脚本内容，足够长，便于测试审批签名。\n", encoding="utf-8")
            tts_path.write_text("# wechat_video TTS口播脚本\n\n## 01. cover_01\n\n这是第一版 TTS 视频脚本内容，足够长，便于测试审批签名。\n", encoding="utf-8")

            signature = pipeline._video_script_signature(layout, "wechat")
            set_step(
                root,
                "approve_video_scripts",
                DONE,
                message="approved",
                meta={"platforms": ["wechat"], "signatures": {"wechat": signature}},
            )

            voice_path.write_text("# wechat_video 口播脚本\n\n## 01. cover_01\n\n这是修改后的第二版视频脚本内容，应该触发重新审批。\n", encoding="utf-8")
            pipeline._ensure_video_scripts_approval_current(root, layout, ["wechat"])

            state = load_state(root)
            self.assertEqual(state["steps"]["approve_video_scripts"]["status"], "blocked")
            self.assertIn("重新确认脚本", state["steps"]["approve_video_scripts"]["message"])

    def test_approve_video_scripts_generates_tts_from_approved_voice_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            layout = resolve_layout(root)
            layout.ensure_structure()

            set_step(root, "derive_video_scripts", DONE, message="ready")
            voice_path = layout.video_voice_script_path("wechat")
            voice_path.write_text(
                "\n".join(
                    [
                        "# wechat_video 口播脚本",
                        "",
                        "## 01. cover_01",
                        "- 图片：images/wechat/cover_01.jpg",
                        "",
                        "ChatGPT 订阅用户变化不大。",
                        "例如长链路、长文档。",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            args = Namespace(topic_root=str(root), mode="prod", platforms="wechat")
            pipeline.intent_approve_video_scripts(args)

            tts_text = layout.video_voice_tts_script_path("wechat").read_text(encoding="utf-8")
            self.assertIn("ChatGPT 订阅用户变化不大。", tts_text)
            self.assertNotIn("Chat G P T", tts_text)
            self.assertIn("例如长链路、长文档。", tts_text.replace("\n", " "))
            state = load_state(root)
            self.assertEqual(state["steps"]["approve_video_scripts"]["status"], DONE)


if __name__ == "__main__":
    unittest.main()
