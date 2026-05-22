from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import generate_personal_ip as gpi  # noqa: E402


class GeneratePersonalIpTests(unittest.TestCase):
    def test_select_photos_prefers_primary_face(self) -> None:
        root = Path("/photos")
        photos = [
            gpi.PhotoInfo(root / "IMG_1.HEIC", 5712, 4284, 70, "large"),
            gpi.PhotoInfo(root / "00 头像.png", 1086, 1448, 999, "primary"),
            gpi.PhotoInfo(root / "头像.JPG", 1540, 2054, 999, "primary"),
            gpi.PhotoInfo(root / "wide.jpg", 4032, 3024, 55, "wide"),
        ]
        with mock.patch.object(gpi, "scan_photos", return_value=photos):
            selected = gpi.select_photos(root, 3)

        self.assertEqual(selected[0].path.name, "00 头像.png")
        self.assertEqual(len(selected), 3)

    def test_build_profile_prompt_only_writes_expected_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            photo_dir = Path(tmp) / "photos"
            photo_dir.mkdir()
            out = Path(tmp) / "out"
            photos = [
                gpi.PhotoInfo(photo_dir / "头像.JPG", 1540, 2054, 100, "主头像"),
                gpi.PhotoInfo(photo_dir / "body.jpg", 2316, 3088, 80, "竖图"),
            ]
            for photo in photos:
                photo.path.write_bytes(b"fake-jpeg")
            args = type(
                "Args",
                (),
                {
                    "photo_dir": str(photo_dir),
                    "out": str(out),
                    "max_photos": 5,
                },
            )()
            with mock.patch.object(gpi, "select_photos", return_value=photos), mock.patch.object(
                gpi,
                "convert_to_jpeg",
                side_effect=lambda src, dst: dst.write_bytes(b"converted") or dst,
            ):
                gpi.build_profile(args)

            selected = json.loads((out / "profile" / "selected_photos.json").read_text(encoding="utf-8"))
            self.assertTrue(selected[0]["primary_face_reference"])
            self.assertTrue((out / "profile" / "prompts" / "front.md").exists())
            self.assertTrue((out / "profile" / "profile-card.md").exists())
            metadata = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
            self.assertFalse(metadata["planned_outputs"][0]["rendered"])
            self.assertEqual(metadata["planned_outputs"][0]["renderer"], "codex_builtin_image_gen")

    def test_cover_prompt_only_writes_five_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile"
            profile.mkdir()
            source = Path(tmp) / "source.jpg"
            source.write_bytes(b"fake-jpeg")
            (profile / "selected_photos.json").write_text(
                json.dumps(
                    [{"path": str(source), "width": 1200, "height": 1600, "reason": "test"}],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            out = Path(tmp) / "covers"
            style_dir = Path(tmp) / "style"
            style_dir.mkdir()
            (style_dir / "00.整体风格提示词.md").write_text(
                "标题保持大字，醒目。\n图像整体风格偏小红书封面风。",
                encoding="utf-8",
            )
            (style_dir / "00.style-参考.png").write_bytes(b"fake-style")
            topic_dir = Path(tmp) / "topic"
            case_dir = topic_dir / "案例"
            case_dir.mkdir(parents=True)
            (case_dir / "案例1.png").write_bytes(b"fake-case")
            args = type(
                "Args",
                (),
                {
                    "title": "AI 时代，个人品牌为什么越来越重要",
                    "profile": str(profile),
                    "out": str(out),
                    "style_dir": str(style_dir),
                    "topic_dir": str(topic_dir),
                    "case_dir": "",
                },
            )()
            with mock.patch.object(
                gpi,
                "convert_to_jpeg",
                side_effect=lambda src, dst: dst.write_bytes(b"converted") or dst,
            ):
                gpi.generate_covers(args)

            self.assertTrue((out / "prompts" / "douyin.md").exists())
            self.assertTrue((out / "prompts" / "xhs.md").exists())
            self.assertTrue((out / "prompts" / "bilibili_4x3.md").exists())
            self.assertTrue((out / "prompts" / "bilibili_16x9.md").exists())
            self.assertTrue((out / "prompts" / "wechat_channels.md").exists())
            douyin_prompt = (out / "prompts" / "douyin.md").read_text(encoding="utf-8")
            bilibili_4x3_prompt = (out / "prompts" / "bilibili_4x3.md").read_text(encoding="utf-8")
            bilibili_16x9_prompt = (out / "prompts" / "bilibili_16x9.md").read_text(encoding="utf-8")
            wechat_channels_prompt = (out / "prompts" / "wechat_channels.md").read_text(encoding="utf-8")
            self.assertIn("centered 3:4 safe crop", douyin_prompt)
            self.assertIn("标题保持大字", douyin_prompt)
            self.assertIn(f"整体风格提示词来源：{gpi.DEFAULT_STYLE_PROMPT_LINK}", douyin_prompt)
            self.assertIn(f"封面风格参考图来源：{(style_dir / '00.style-参考.png').resolve()}", douyin_prompt)
            self.assertIn("话题案例图参考", douyin_prompt)
            self.assertIn("Bilibili direct 4:3 cover", bilibili_4x3_prompt)
            self.assertIn("Bilibili native 16:9 cover", bilibili_16x9_prompt)
            self.assertIn("do not reserve left/right disposable margins", bilibili_16x9_prompt)
            self.assertIn("centered 3:4 safe crop", wechat_channels_prompt)
            metadata = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(len(metadata["covers"]), 5)
            self.assertEqual(metadata["style_reference_images"], [str((style_dir / "00.style-参考.png").resolve())])
            self.assertEqual(metadata["case_reference_images"], [str((case_dir / "案例1.png").resolve())])
            self.assertIn(str(gpi.DEFAULT_IP_CUTOUT_REFERENCE.resolve()), metadata["ip_cutout_reference_images"])
            ratios = {item["platform"]: item["aspect_ratio"] for item in metadata["covers"]}
            self.assertEqual(ratios["douyin"], "9:16")
            self.assertEqual(ratios["xhs"], "3:4")
            self.assertEqual(ratios["bilibili_4x3"], "4:3")
            self.assertEqual(ratios["bilibili_16x9"], "16:9")
            self.assertEqual(ratios["wechat_channels"], "9:16")


if __name__ == "__main__":
    unittest.main()
