from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "pipeline_config.py"
SPEC = importlib.util.spec_from_file_location("pipeline_config", MODULE_PATH)
pipeline_config = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["pipeline_config"] = pipeline_config
SPEC.loader.exec_module(pipeline_config)


def test_load_pipeline_config_uses_repo_local_jianying_root_on_linux() -> None:
    repo_root = Path("/tmp/aki-skills")
    with mock.patch.object(pipeline_config, "_repo_root", return_value=repo_root):
        with mock.patch("sys.platform", "linux"):
            with mock.patch.dict("os.environ", {}, clear=True):
                cfg = pipeline_config.load_pipeline_config()

    assert cfg.jy_projects_root == repo_root / "skills" / "aki-image-article-video" / ".local" / "jianying_projects" / "com.lveditor.draft"
