from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "pipeline.py"
SPEC = importlib.util.spec_from_file_location("pipeline", MODULE_PATH)
pipeline = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(pipeline)


def test_intent_render_images_passes_image_provider() -> None:
    args = Namespace(
        topic_root="/tmp/topic",
        mode="prod",
        platforms="auto",
        unit_cost=0.6,
        image_provider="openrouter",
    )

    with mock.patch.object(pipeline, "_ensure_topic_root", return_value=Path("/tmp/topic")), mock.patch.object(
        pipeline,
        "_ensure_core_note_approval_current",
    ), mock.patch.object(
        pipeline,
        "_require_done",
    ), mock.patch.object(
        pipeline,
        "load_state",
        return_value={"mode": "prod"},
    ), mock.patch.object(
        pipeline,
        "_run_python",
        return_value=0,
    ) as run_mock:
        pipeline.intent_render_images(args)

    passed = run_mock.call_args.args[1]
    assert "--image-provider" in passed
    assert "openrouter" in passed
