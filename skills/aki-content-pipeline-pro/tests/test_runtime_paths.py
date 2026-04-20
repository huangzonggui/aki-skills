from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[3] / "shared" / "aki_runtime.py"
SPEC = importlib.util.spec_from_file_location("aki_runtime", MODULE_PATH)
aki_runtime = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(aki_runtime)


def test_content_topics_root_uses_obsidian_env() -> None:
    with mock.patch.dict(os.environ, {"AKI_OBSIDIAN_VAULT_ROOT": "/srv/aki/obsidian/Aki数字资产"}, clear=False):
        got = aki_runtime.content_topics_root()

    assert got == Path("/srv/aki/obsidian/Aki数字资产/02-IP个人话题")


def test_default_jianying_projects_root_is_repo_local_on_linux() -> None:
    repo_root = Path("/tmp/aki-skills")
    with mock.patch("sys.platform", "linux"):
        got = aki_runtime.default_jianying_projects_root(repo_root=repo_root)

    assert got == repo_root / "skills" / "aki-image-article-video" / ".local" / "jianying_projects" / "com.lveditor.draft"


def test_default_publish_profile_root_uses_linux_share_dir() -> None:
    with mock.patch("sys.platform", "linux"):
        with mock.patch.object(Path, "home", return_value=Path("/home/aki")):
            got = aki_runtime.default_publish_profile_root()

    assert got == Path("/home/aki/.local/share/aki-skills/publisher-profiles")
