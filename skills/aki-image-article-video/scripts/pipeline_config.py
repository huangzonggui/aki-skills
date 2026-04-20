#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULTS_FILE = SKILL_ROOT / "config" / "defaults.json"
REPO_ROOT = Path(os.getenv("AKI_SKILLS_REPO_ROOT", "")).expanduser().resolve() if os.getenv("AKI_SKILLS_REPO_ROOT") else SKILL_ROOT.parent.parent
SHARED_DIR = REPO_ROOT / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from aki_runtime import default_ai_keys_env_path, default_jianying_projects_root, repo_root  # noqa: E402


def _repo_root() -> Path:
    return repo_root(SCRIPT_DIR)


def _fallback_defaults() -> dict[str, str]:
    root = _repo_root()
    return {
        "jy_projects_root_default": str(default_jianying_projects_root(repo_root_path=root)),
        "ai_keys_env_path_default": str(default_ai_keys_env_path()),
        "voice_profile_path_default": "skills/aki-image-article-video/.local/voice_profiles.json",
        "jy_cache_music_dir_default": "skills/aki-image-article-video/.local/jianying_cache/music",
        "runtime_reports_dir_default": "skills/aki-image-article-video/.local/runtime_reports",
    }


def _resolve_path(raw: str) -> Path:
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p
    if raw.startswith("skills/"):
        return (_repo_root() / raw).resolve()
    return (SKILL_ROOT / raw).resolve()


def _should_keep_path_override(value: str) -> bool:
    if sys.platform != "darwin" and value.startswith("/Users/"):
        return False
    if sys.platform == "darwin" and value.startswith("/srv/"):
        return False
    return True


def _load_defaults_json() -> dict[str, Any]:
    fallback = _fallback_defaults()
    if not DEFAULTS_FILE.exists():
        return dict(fallback)
    try:
        data = json.loads(DEFAULTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    merged = dict(fallback)
    for key, value in data.items():
        if not isinstance(value, str) or not value.strip():
            continue
        if key in {"jy_projects_root_default", "ai_keys_env_path_default", "jy_cache_music_dir_default"}:
            if not _should_keep_path_override(value):
                continue
        merged[key] = value
    return merged


@dataclass
class PipelineConfig:
    jy_projects_root: Path
    ai_keys_env_path: Path
    voice_profile_path: Path
    jy_cache_music_dir: Path
    runtime_reports_dir: Path

    def ensure_local_dirs(self) -> None:
        self.voice_profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_reports_dir.mkdir(parents=True, exist_ok=True)


def load_pipeline_config(overrides: dict[str, str] | None = None) -> PipelineConfig:
    raw = _load_defaults_json()
    if overrides:
        raw.update({k: v for k, v in overrides.items() if v})

    # env override keeps runtime flexible for other machines
    jy_root = os.getenv("JY_PROJECTS_ROOT", raw["jy_projects_root_default"])
    keys_env = os.getenv("AI_KEYS_ENV_PATH", raw["ai_keys_env_path_default"])
    voice_profile = os.getenv("VOICE_PROFILE_PATH", raw["voice_profile_path_default"])
    bgm_dir = os.getenv("JY_CACHE_MUSIC_DIR", raw["jy_cache_music_dir_default"])
    runtime_reports = os.getenv("RUNTIME_REPORTS_DIR", raw["runtime_reports_dir_default"])

    cfg = PipelineConfig(
        jy_projects_root=_resolve_path(jy_root),
        ai_keys_env_path=_resolve_path(keys_env),
        voice_profile_path=_resolve_path(voice_profile),
        jy_cache_music_dir=_resolve_path(bgm_dir),
        runtime_reports_dir=_resolve_path(runtime_reports),
    )
    cfg.ensure_local_dirs()
    return cfg
