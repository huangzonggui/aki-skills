#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
REPO_ROOT = SKILL_ROOT.parent.parent
DEFAULTS_FILE = SKILL_ROOT / "config" / "defaults.json"


FALLBACK_DEFAULTS = {
    "jy_projects_root_default": "/Users/aki/Movies/JianyingPro/User Data/Projects/com.lveditor.draft",
    "ai_keys_env_path_default": "/Users/aki/.config/ai/keys.env",
    "voice_profile_path_default": "skills/aki-image-article-video/.local/voice_profiles.json",
    "jy_cache_music_dir_default": "/Users/aki/Movies/JianyingPro/User Data/Cache/music",
    "runtime_reports_dir_default": "skills/aki-image-article-video/.local/runtime_reports",
}


def _resolve_path(raw: str) -> Path:
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p
    if raw.startswith("skills/"):
        return (REPO_ROOT / raw).resolve()
    return (SKILL_ROOT / raw).resolve()


def _load_defaults_json() -> dict[str, Any]:
    if not DEFAULTS_FILE.exists():
        return dict(FALLBACK_DEFAULTS)
    try:
        data = json.loads(DEFAULTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    merged = dict(FALLBACK_DEFAULTS)
    merged.update({k: v for k, v in data.items() if isinstance(v, str) and v.strip()})
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

