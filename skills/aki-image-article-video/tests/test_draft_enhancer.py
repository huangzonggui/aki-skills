from __future__ import annotations

import sys
import unittest
from unittest import mock
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import draft_enhancer  # noqa: E402


class DraftEnhancerTests(unittest.TestCase):
    def test_apply_group_zoom_ii_uses_group_animation(self) -> None:
        data = {
            "materials": {"material_animations": []},
            "tracks": [
                {
                    "type": "video",
                    "segments": [
                        {
                            "id": "seg-1",
                            "clip": {"scale": {"x": 1.0, "y": 1.0}},
                            "extra_material_refs": [],
                        }
                    ],
                }
            ],
        }

        report = draft_enhancer.apply_group_zoom_ii(data)

        self.assertEqual(report["preset"], "zoom_group_ii")
        animation_pack = data["materials"]["material_animations"][0]["animations"]
        self.assertEqual(len(animation_pack), 1)
        self.assertEqual(animation_pack[0]["type"], "group")
        self.assertEqual(animation_pack[0]["name"], "缩放 II")

    def test_apply_light_zoom_adds_in_and_out_scale_animations(self) -> None:
        data = {
            "materials": {"material_animations": []},
            "tracks": [
                {
                    "type": "video",
                    "segments": [
                        {
                            "id": "seg-1",
                            "clip": {"scale": {"x": 1.0, "y": 1.0}},
                            "extra_material_refs": [],
                        }
                    ],
                }
            ],
        }

        report = draft_enhancer.apply_light_zoom(data)

        self.assertEqual(report["changed_segments"], 1)
        self.assertEqual(report["added_animations"], 1)
        animation_pack = data["materials"]["material_animations"][0]["animations"]
        animation_types = {item["type"] for item in animation_pack}
        animation_names = {item["name"] for item in animation_pack}
        self.assertEqual(animation_types, {"in", "out"})
        self.assertTrue({"缩小", "轻微放大"} & animation_names)

    def test_add_bgm_track_uses_minus_10db_as_default_gain(self) -> None:
        data = {
            "materials": {"audios": []},
            "tracks": [],
        }

        with mock.patch.object(draft_enhancer, "probe_duration_us", return_value=5_000_000):
            report = draft_enhancer.add_bgm_track(
                data=data,
                bgm_path=Path("/tmp/fake.mp3"),
                total_us=10_000_000,
            )

        bgm_track = next(track for track in data["tracks"] if track["type"] == "audio")
        first_segment = bgm_track["segments"][0]
        self.assertEqual(report["speech_db"], -10.0)
        self.assertAlmostEqual(first_segment["volume"], draft_enhancer._db_to_gain(-10.0), places=6)


if __name__ == "__main__":
    unittest.main()
