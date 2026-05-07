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
            gpi.PhotoInfo(root / "头像.JPG", 1540, 2054, 999, "primary"),
            gpi.PhotoInfo(root / "wide.jpg", 4032, 3024, 55, "wide"),
        ]
        with mock.patch.object(gpi, "scan_photos", return_value=photos):
            selected = gpi.select_photos(root, 3)

        self.assertEqual(selected[0].path.name, "头像.JPG")
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
                    "confirm": False,
                    "image_provider": "comfly",
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
            self.assertFalse(metadata["renders"][0]["rendered"])

    def test_cover_prompt_only_writes_three_platforms(self) -> None:
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
            args = type(
                "Args",
                (),
                {
                    "title": "AI 时代，个人品牌为什么越来越重要",
                    "profile": str(profile),
                    "out": str(out),
                    "confirm": False,
                    "image_provider": "comfly",
                },
            )()
            with mock.patch.object(
                gpi,
                "convert_to_jpeg",
                side_effect=lambda src, dst: dst.write_bytes(b"converted") or dst,
            ):
                gpi.generate_covers(args)

            self.assertTrue((out / "prompts" / "xhs.md").exists())
            self.assertTrue((out / "prompts" / "wechat.md").exists())
            self.assertTrue((out / "prompts" / "video.md").exists())
            metadata = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(len(metadata["covers"]), 3)


if __name__ == "__main__":
    unittest.main()
