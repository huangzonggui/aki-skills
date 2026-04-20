#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


REPO_URL = "https://github.com/huangzonggui/aki-skills.git"


def _git_stdout(args: list[str], cwd: Path) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.strip() or cp.stdout.strip() or f"git {' '.join(args)} failed")
    return cp.stdout.strip()


def detect_existing_repo(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        repo_dir = candidate.expanduser().resolve()
        if not (repo_dir / ".git").exists():
            continue
        try:
            origin = _git_stdout(["config", "--get", "remote.origin.url"], repo_dir)
        except Exception:
            continue
        if "huangzonggui/aki-skills.git" in origin:
            return repo_dir
    return None


def plan_sync_action(existing_repo: Path | None, target_dir: Path) -> dict[str, str]:
    if existing_repo is not None:
        return {"action": "pull", "repo_path": str(existing_repo)}
    return {"action": "clone", "repo_path": str(target_dir.expanduser().resolve())}


def sync_repo(existing_repo: Path | None, target_dir: Path) -> dict[str, str]:
    plan = plan_sync_action(existing_repo=existing_repo, target_dir=target_dir)
    repo_path = Path(plan["repo_path"]).expanduser().resolve()

    if plan["action"] == "clone":
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        cp = subprocess.run(
            ["git", "clone", REPO_URL, str(repo_path)],
            text=True,
            capture_output=True,
            check=False,
        )
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr.strip() or cp.stdout.strip() or "git clone failed")
    else:
        _git_stdout(["fetch", "origin"], repo_path)
        _git_stdout(["checkout", "main"], repo_path)
        _git_stdout(["pull", "--ff-only", "origin", "main"], repo_path)

    commit_sha = _git_stdout(["rev-parse", "HEAD"], repo_path)
    return {
        "action": plan["action"],
        "repo_path": str(repo_path),
        "commit_sha": commit_sha,
    }


def _default_candidates() -> list[Path]:
    home = Path.home()
    return [
        home / "openclaw-aki-skills",
        home / "aki-skills",
        home / ".openclaw" / "workspace" / "aki-skills",
        Path("/srv/aki/aki-skills"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure aki-skills runtime repo exists and is up to date")
    parser.add_argument("--candidate", action="append", default=[], help="Candidate runtime repo dir to inspect")
    parser.add_argument("--target-dir", default=str(Path.home() / "openclaw-aki-skills"))
    args = parser.parse_args()

    candidates = [Path(item).expanduser() for item in args.candidate] or _default_candidates()
    existing_repo = detect_existing_repo(candidates)
    result = sync_repo(existing_repo=existing_repo, target_dir=Path(args.target_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
