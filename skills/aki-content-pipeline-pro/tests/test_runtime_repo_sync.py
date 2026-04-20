from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "runtime_repo_sync.py"
SPEC = importlib.util.spec_from_file_location("runtime_repo_sync", MODULE_PATH)
runtime_repo_sync = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(runtime_repo_sync)


def test_detect_existing_repo_returns_matching_origin(tmp_path: Path) -> None:
    repo_dir = tmp_path / "aki-skills"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()

    def fake_git(args: list[str], cwd: Path) -> str:
        assert cwd == repo_dir
        if args == ["config", "--get", "remote.origin.url"]:
            return "https://github.com/huangzonggui/aki-skills.git"
        raise AssertionError(args)

    with mock.patch.object(runtime_repo_sync, "_git_stdout", side_effect=fake_git):
        got = runtime_repo_sync.detect_existing_repo([repo_dir])

    assert got == repo_dir


def test_plan_sync_action_prefers_clone_when_no_repo_found(tmp_path: Path) -> None:
    target = tmp_path / "runtime"
    action = runtime_repo_sync.plan_sync_action(existing_repo=None, target_dir=target)
    assert action["action"] == "clone"
    assert action["repo_path"] == str(target)
