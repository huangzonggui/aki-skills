from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import build_video_from_article_assets  # noqa: E402


class SubtitleStyleTests(unittest.TestCase):
    def test_apply_subtitle_style_to_materials_uses_yellow_preset(self) -> None:
        text_material = {
            "content": json.dumps(
                {
                    "styles": [
                        {
                            "fill": {
                                "alpha": 1.0,
                                "content": {
                                    "render_type": "solid",
                                    "solid": {"alpha": 1.0, "color": [1.0, 1.0, 1.0]},
                                },
                            },
                            "range": [0, 4],
                            "size": 5.2,
                            "bold": False,
                            "italic": False,
                            "underline": False,
                            "strokes": [],
                            "font": {"id": "7200743888816968247", "path": "D:"},
                        }
                    ],
                    "text": "测试字幕",
                },
                ensure_ascii=False,
            )
        }

        report = build_video_from_article_assets.apply_subtitle_style_to_materials(
            [text_material],
            subtitle_font="莫雪体",
            subtitle_font_size=10.0,
            subtitle_style="yellow_preset",
        )

        styled = json.loads(text_material["content"])["styles"][0]
        fill = styled["fill"]["content"]["solid"]["color"]
        self.assertEqual(report["font_name"], "莫雪体")
        self.assertEqual(report["font_size"], 10.0)
        self.assertEqual(report["style_mode"], "yellow_preset")
        self.assertEqual(fill, [1.0, 0.862745, 0.14902])
        self.assertTrue(styled["strokes"])


if __name__ == "__main__":
    unittest.main()
