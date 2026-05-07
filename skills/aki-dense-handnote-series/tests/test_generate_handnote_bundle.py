from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import generate_handnote_bundle as ghb


class _FakeRouter:
    def __init__(self) -> None:
        self.calls = []

    def render_batch(self, requests):
        self.calls = list(requests)
        for request in self.calls:
            request.output_path.parent.mkdir(parents=True, exist_ok=True)
            request.output_path.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            )
        return None


class GenerateHandnoteBundleTests(unittest.TestCase):
    def test_render_images_uses_shared_router(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            cover_output = tmp_path / "cover.png"
            series_dir = tmp_path / "series"
            router = _FakeRouter()

            with patch.object(
                ghb,
                "build_image_router",
                return_value=router,
            ):
                generated_cover, generated = ghb._render_images(
                    "cover prompt",
                    ["page 1", "page 2"],
                    cover_output,
                    series_dir,
                    Path("/tmp/unused"),
                    "",
                    0,
                    "openrouter",
                )

        self.assertIsNotNone(generated_cover)
        self.assertEqual(len(generated), 2)
        self.assertEqual(len(router.calls), 3)
