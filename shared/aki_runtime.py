from __future__ import annotations

import os
import sys
from pathlib import Path


DEFAULT_VAULT_NAME = "Aki数字资产"
DEFAULT_TOPICS_DIRNAME = "02-IP个人话题"


def repo_root(start: Path | None = None) -> Path:
    raw = os.getenv("AKI_SKILLS_REPO_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()

    probe = (start or Path(__file__).resolve()).expanduser().resolve()
    current = probe if probe.is_dir() else probe.parent
    for candidate in [current, *current.parents]:
        if (candidate / "skills").is_dir() and (candidate / "README.md").exists():
            return candidate.resolve()
    return Path(__file__).resolve().parents[1]


def skill_path(skill_name: str, *parts: str, repo_root_path: Path | None = None) -> Path:
    base = (repo_root_path or repo_root()).resolve() / "skills" / skill_name
    return base.joinpath(*parts)


def default_ai_keys_env_path() -> Path:
    raw = os.getenv("AI_KEYS_ENV_PATH", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".config" / "ai" / "keys.env").expanduser().resolve()


def obsidian_vault_root() -> Path:
    raw = os.getenv("AKI_OBSIDIAN_VAULT_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()

    candidates = [
        Path("/srv/aki/obsidian") / DEFAULT_VAULT_NAME,
        Path.home() / "Documents" / "ObsidianVaults" / DEFAULT_VAULT_NAME,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0]


def content_topics_root() -> Path:
    raw = os.getenv("AKI_CONTENT_TOPICS_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return obsidian_vault_root() / DEFAULT_TOPICS_DIRNAME


def default_publish_profile_root() -> Path:
    raw = os.getenv("AKI_PUBLISH_PROFILE_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "aki-skills" / "publisher-profiles"
    if sys.platform.startswith("win"):
        appdata = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
        return appdata / "aki-skills" / "publisher-profiles"
    return Path.home() / ".local" / "share" / "aki-skills" / "publisher-profiles"


def default_publish_profile(name: str = "zimeiti-publisher") -> Path:
    return default_publish_profile_root() / name


def default_jianying_projects_root(
    repo_root_path: Path | None = None,
    repo_root: Path | None = None,
) -> Path:
    raw = os.getenv("JY_PROJECTS_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Movies" / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft"
    if sys.platform.startswith("win"):
        appdata = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return appdata / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft"
    base = repo_root_path or repo_root or globals()["repo_root"]()
    return base / "skills" / "aki-image-article-video" / ".local" / "jianying_projects" / "com.lveditor.draft"


def default_jianying_sync_root() -> Path | None:
    raw = os.getenv("JY_SYNC_PROJECTS_ROOT", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def default_chat_session_store(repo_root_path: Path | None = None) -> Path:
    raw = os.getenv("AKI_CHAT_SESSION_STORE", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    base = repo_root_path or repo_root()
    return base / "skills" / "aki-content-pipeline-pro" / ".local" / "chat_sessions.json"


def default_private_script_asset_root() -> Path:
    raw = os.getenv("AKI_PRIVATE_SCRIPT_ASSET_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return obsidian_vault_root() / DEFAULT_TOPICS_DIRNAME / "口播脚本资产"


def default_jianying_editor_root() -> Path:
    raw = os.getenv("JY_EDITOR_SKILL_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home() / ".agents" / "skills" / "jianying-editor"


def default_auto_exporter_path() -> Path:
    raw = os.getenv("JY_AUTO_EXPORTER_SCRIPT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return default_jianying_editor_root() / "scripts" / "auto_exporter.py"
