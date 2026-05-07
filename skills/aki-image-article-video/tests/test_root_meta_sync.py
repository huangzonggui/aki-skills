from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import build_video_from_article_assets as builder  # noqa: E402


class RootMetaSyncTests(unittest.TestCase):
    def test_sync_root_meta_entry_updates_draft_meta_and_prunes_suffix_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_root = Path(tmpdir)
            draft_name = "demo_douyin"
            draft_dir = projects_root / draft_name
            draft_dir.mkdir()

            (draft_dir / "draft_content.json").write_text(
                json.dumps({"duration": 123_000_000}, ensure_ascii=False),
                encoding="utf-8",
            )
            (draft_dir / "draft_info.json").write_text("{}", encoding="utf-8")
            (draft_dir / "draft_cover.jpg").write_bytes(b"jpg")
            (draft_dir / "draft_meta_info.json").write_text(
                json.dumps(
                    {
                        "draft_id": "META-DRAFT-ID",
                        "draft_name": draft_name,
                        "draft_fold_path": str(draft_dir),
                        "draft_root_path": str(projects_root),
                        "tm_duration": 0,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            root_meta = {
                "all_draft_store": [
                    {
                        "draft_name": f"{draft_name} (1)",
                        "draft_fold_path": str(projects_root / f"{draft_name} (1)"),
                        "draft_id": "BAD-1",
                        "tm_duration": 999,
                    },
                    {
                        "draft_name": f"{draft_name}(1)",
                        "draft_fold_path": str(projects_root / f"{draft_name}(1)"),
                        "draft_id": "BAD-2",
                        "tm_duration": 999,
                    },
                    {
                        "draft_name": "other_topic",
                        "draft_fold_path": str(projects_root / "other_topic"),
                        "draft_id": "KEEP-ME",
                        "tm_duration": 456,
                    },
                ],
                "draft_ids": 3,
            }
            (projects_root / "root_meta_info.json").write_text(
                json.dumps(root_meta, ensure_ascii=False),
                encoding="utf-8",
            )

            builder.sync_root_meta_entry(projects_root, draft_name)

            updated_root = json.loads((projects_root / "root_meta_info.json").read_text(encoding="utf-8"))
            matches = [
                entry
                for entry in updated_root["all_draft_store"]
                if builder._normalize_draft_identity(entry.get("draft_name")) == draft_name
            ]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["draft_fold_path"], str(draft_dir))
            self.assertEqual(matches[0]["tm_duration"], 123_000_000)
            self.assertEqual(matches[0]["draft_id"], "META-DRAFT-ID")

            updated_meta = json.loads((draft_dir / "draft_meta_info.json").read_text(encoding="utf-8"))
            self.assertEqual(updated_meta["tm_duration"], 123_000_000)
            self.assertEqual(updated_meta["draft_id"], "META-DRAFT-ID")
            self.assertEqual(updated_meta["draft_fold_path"], str(draft_dir))


if __name__ == "__main__":
    unittest.main()
