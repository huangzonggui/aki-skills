from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import collect_sources  # noqa: E402


class CollectSourcesTests(unittest.TestCase):
    def test_wechat_url_without_fetchable_body_creates_manual_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            refs_dir = Path(tmp)

            with mock.patch.object(collect_sources, "best_effort_fetch", return_value=""):
                result = collect_sources.ingest_one(
                    "https://mp.weixin.qq.com/s/example",
                    refs_dir,
                    Path("/missing-youtube-runner"),
                    Path("/missing-youtube-download"),
                    1,
                )

            self.assertEqual(result["status"], "manual_required")
            manual_path = Path(str(result["manual_input_path"]))
            self.assertTrue(manual_path.exists())
            self.assertIn("自动抓取正文失败", manual_path.read_text(encoding="utf-8"))
            self.assertTrue(Path(str(result["raw_path"])).exists())
            self.assertTrue(Path(str(result["clean_path"])).exists())

    def test_wechat_url_with_fetchable_body_uses_generic_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            refs_dir = Path(tmp)

            with mock.patch.object(collect_sources, "best_effort_fetch", return_value="正文" * 300):
                result = collect_sources.ingest_one(
                    "https://mp.weixin.qq.com/s/example",
                    refs_dir,
                    Path("/missing-youtube-runner"),
                    Path("/missing-youtube-download"),
                    1,
                )

            self.assertEqual(result["status"], "ok")
            self.assertNotIn("manual_input_path", result)


if __name__ == "__main__":
    unittest.main()
