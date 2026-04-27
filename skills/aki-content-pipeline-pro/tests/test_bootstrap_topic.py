from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import bootstrap_topic  # noqa: E402


def test_init_topic_creates_only_meta_until_outputs_exist() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base_dir = Path(tmp)
        argv = [
            "bootstrap_topic.py",
            "--cwd",
            str(base_dir),
            "--title",
            "Lazy Directories",
            "--mode",
            "prod",
            "--timestamp",
            "20260427-1200",
        ]
        with mock.patch.object(sys, "argv", argv):
            assert bootstrap_topic.main() == 0

        topic_root = base_dir / "0. Lazy Directories-20260427-1200"
        assert topic_root.is_dir()
        assert (topic_root / "meta" / "topic_meta.json").is_file()
        assert (topic_root / "meta" / "state.json").is_file()

        for name in ("refs", "copies", "prompts", "images", "video"):
            assert not (topic_root / name).exists()
