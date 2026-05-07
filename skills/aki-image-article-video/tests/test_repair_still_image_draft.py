from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import repair_still_image_draft  # noqa: E402


class RepairStillImageDraftTests(unittest.TestCase):
    def test_plan_foreground_layout_uses_content_bbox_to_shift_center(self) -> None:
        plan = repair_still_image_draft.plan_foreground_layout(
            image_size=(1000, 2000),
            bbox=(80, 220, 520, 1600),
            target_size=(1440, 2560),
        )

        self.assertEqual(plan["foreground_size"], (1280, 2560))
        self.assertGreater(plan["foreground_offset"][0], 80)
        self.assertEqual(plan["foreground_offset"][1], 0)


if __name__ == "__main__":
    unittest.main()
