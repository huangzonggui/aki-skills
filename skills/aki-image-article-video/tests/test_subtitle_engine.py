from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import subtitle_engine  # noqa: E402


class SubtitleEngineTests(unittest.TestCase):
    def test_merge_sentence_fragments_combines_short_adjacent_pieces(self) -> None:
        segments = [
            {"start": 0.0, "end": 0.6, "text": "它开始", "char_len": 3},
            {"start": 0.6, "end": 1.3, "text": "往工作站", "char_len": 4},
            {"start": 1.3, "end": 2.4, "text": "和机器人一路长过去。", "char_len": 10},
        ]

        merged = subtitle_engine._merge_sentence_fragments(
            segments,
            max_chars=26,
            max_duration=3.2,
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["text"], "它开始往工作站和机器人一路长过去。")
        self.assertAlmostEqual(merged[0]["end"], 2.4)


if __name__ == "__main__":
    unittest.main()
