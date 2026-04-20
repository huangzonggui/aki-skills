from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import build_video_file  # noqa: E402
import pipeline as build_video_file_pipeline  # noqa: E402
from topic_layout import resolve_layout  # noqa: E402


class BuildVideoFileTests(unittest.TestCase):
    def test_build_stage_assets_prefers_tts_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            layout = resolve_layout(root)
            layout.ensure_structure()

            image_path = root / "sample.jpg"
            image_path.write_bytes(b"fake")

            timeline = {
                "segments": [
                    {
                        "slot": 1,
                        "image_path": str(image_path),
                        "script": "展示稿第一句",
                        "tts_script": "口播稿第一句",
                    }
                ]
            }
            layout.video_timeline_path("wechat").write_text(
                json.dumps(timeline, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            _, stage_script, script_source = build_video_file._build_stage_assets(layout, "wechat")

            self.assertEqual(
                stage_script.read_text(encoding="utf-8").strip(),
                "口播稿第一句",
            )
            self.assertEqual(script_source, str(layout.video_timeline_path("wechat")))

    def test_build_stage_assets_refreshes_stage_script_when_override_is_newer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            layout = resolve_layout(root)
            layout.ensure_structure()

            image_path = root / "sample.jpg"
            image_path.write_bytes(b"fake")

            timeline = {
                "segments": [
                    {
                        "slot": 1,
                        "image_path": str(image_path),
                        "script": "展示稿第一句",
                        "tts_script": "时间轴口播第一句",
                    }
                ]
            }
            layout.video_timeline_path("wechat").write_text(
                json.dumps(timeline, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            stage_script = layout.video_stage_script_path("wechat")
            stage_script.parent.mkdir(parents=True, exist_ok=True)
            stage_script.write_text("旧的缓存稿\n", encoding="utf-8")
            old_mtime = stage_script.stat().st_mtime

            tts_script = layout.video_voice_tts_script_path("wechat")
            tts_script.write_text(
                "\n".join(
                    [
                        "# wechat_video TTS口播脚本",
                        "",
                        "## 01. cover_01",
                        "- 图片：images/wechat/cover_01.jpg",
                        "",
                        "这是新的口播稿。",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            os.utime(tts_script, (old_mtime + 5, old_mtime + 5))

            _, refreshed_stage_script, script_source = build_video_file._build_stage_assets(layout, "wechat")

            self.assertEqual(
                refreshed_stage_script.read_text(encoding="utf-8").strip(),
                "这是新的口播稿。",
            )
            self.assertEqual(script_source, str(tts_script))

    def test_choose_export_strategy_uses_ffmpeg_fallback_on_mac_force_export(self) -> None:
        with mock.patch.object(build_video_file, "_ffmpeg_available", return_value=True):
            strategy = build_video_file._choose_export_strategy(force_export=True, platform_name="darwin")

        self.assertEqual(strategy, "ffmpeg_fallback")

    def test_sync_draft_to_mirror_root_copies_draft_and_root_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source_root = tmp / "drafts"
            source_root.mkdir()
            draft_dir = source_root / "demo_wechat"
            draft_dir.mkdir()
            (draft_dir / "draft_info.json").write_text("{}", encoding="utf-8")
            (source_root / "root_meta_info.json").write_text('{"all_draft_store":[]}', encoding="utf-8")
            mirror_root = tmp / "mirror"

            mirrored = build_video_file._sync_draft_to_mirror_root(draft_dir, mirror_root)

            self.assertEqual(mirrored, mirror_root / "demo_wechat")
            self.assertTrue((mirror_root / "demo_wechat" / "draft_info.json").exists())
            self.assertTrue((mirror_root / "root_meta_info.json").exists())

    def test_rewrite_segment_script_for_tts_normalizes_mixed_terms(self) -> None:
        rewritten = build_video_file_pipeline._rewrite_segment_script_for_tts(
            "黄仁勋说，龙虾是下一个ChatGPT。现在很多Agent已经开始真的干活。"
        )

        self.assertIn("Chat G P T", rewritten)
        self.assertNotIn("ChatGPT", rewritten)
        self.assertIn("智能体", rewritten)


if __name__ == "__main__":
    unittest.main()
