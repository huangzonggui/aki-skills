from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import bgm_selector  # noqa: E402


class BgmSelectorTests(unittest.TestCase):
    def test_favorites_first_mode_prefers_resolved_favorite_commercial_track(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            music_dir = root / "music"
            music_dir.mkdir()
            track = music_dir / "fav.mp3"
            track.write_bytes(b"fake-mp3")

            history_file = root / "bgm_history.json"
            history_file.write_text(
                json.dumps(
                    {
                        "tracks": {
                            str(track.resolve()): {
                                "status": "unknown",
                                "hits": 0,
                                "last_used": 0,
                                "category": "music",
                                "duration_sec": 80,
                            }
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            projects_root = root / "projects"
            project_dir = projects_root / "demo"
            project_dir.mkdir(parents=True)
            (project_dir / "key_value.json").write_text(
                json.dumps(
                    {
                        "entry": {
                            "materialCategory": "audio",
                            "materialSubcategory": "music",
                            "materialThirdcategory": "music_fav",
                            "material_is_purchased": "1",
                            "materialId": "music-1",
                            "materialName": "favorite bgm",
                            "is_favorite": True,
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (project_dir / "draft_content.json").write_text(
                json.dumps(
                    {
                        "materials": {
                            "audios": [
                                {
                                    "path": str(track.resolve()),
                                }
                            ]
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            report = bgm_selector.choose_bgm(
                music_dir=music_dir,
                history_file=history_file,
                mode="favorites_first_controlled_fallback",
                min_music_duration_sec=45.0,
                projects_root=projects_root,
                prefer_jy_favorite_commercial=True,
            )

            self.assertTrue(report["ok"])
            self.assertEqual(report["track_path"], str(track.resolve()))
            self.assertEqual(report["source"], "jy_favorite_commercial_pool")


if __name__ == "__main__":
    unittest.main()
