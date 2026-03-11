#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Any

from pipeline_config import load_pipeline_config


AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"}
SFX_NAME_KEYWORDS = (
    "sfx",
    "fx",
    "音效",
    "爆炸",
    "hit",
    "impact",
    "whoosh",
    "transition",
    "转场",
)


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default)
    if not isinstance(data, dict):
        return dict(default)
    merged = dict(default)
    merged.update(data)
    return merged


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def collect_tracks(music_dir: Path) -> list[Path]:
    tracks: list[Path] = []
    if not music_dir.exists():
        return tracks
    for child in music_dir.iterdir():
        if child.is_file() and child.suffix.lower() in AUDIO_EXTS:
            tracks.append(child.resolve())
    return sorted(tracks, key=lambda p: p.name.lower())


def probe_duration_sec(audio_path: Path) -> float:
    try:
        import subprocess

        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nk=1:nw=1",
                str(audio_path),
            ],
            text=True,
        ).strip()
        return max(0.0, float(out))
    except Exception:
        return 0.0


def detect_track_category(audio_path: Path) -> str:
    name = audio_path.name.lower()
    for kw in SFX_NAME_KEYWORDS:
        if kw in name:
            return "sfx"
    return "music"


def _is_music_entry(meta: dict[str, Any]) -> bool:
    return (
        str(meta.get("materialCategory", "")).strip() == "audio"
        and str(meta.get("materialSubcategory", "")).strip() == "music"
    )


def _is_favorite_music(meta: dict[str, Any]) -> bool:
    if meta.get("is_favorite") is True:
        return True
    third = str(meta.get("materialThirdcategory", "") or "").strip().lower()
    return ("收藏" in third) or (third in {"music_fav", "favorite"})


def _is_commercial_music(meta: dict[str, Any]) -> bool:
    # JianYing local metadata does not expose a strict legal flag consistently.
    # Use purchase/subscription-available marker as practical commercial-safe proxy.
    return str(meta.get("material_is_purchased", "") or "") == "1"


def _normalize_music_path(raw_path: str, music_dir: Path) -> Path | None:
    if not raw_path:
        return None
    p = Path(raw_path).expanduser()
    if p.exists():
        return p.resolve()

    # Some drafts store path under app container prefix. Normalize to configured cache dir.
    marker = "/User Data/Cache/music/"
    text = str(p)
    idx = text.find(marker)
    if idx >= 0:
        suffix = text[idx + len(marker) :]
        alt = (music_dir / suffix).resolve()
        if alt.exists():
            return alt
    return None


def _collect_cache_music_paths_from_project(project_dir: Path, music_dir: Path) -> set[Path]:
    paths: set[Path] = set()
    for fname in ("draft_info.json", "draft_content.json", "template.tmp", "template-2.tmp"):
        p = project_dir / fname
        if not p.exists():
            continue
        payload = _safe_read_json(p)
        if not payload:
            continue
        materials = payload.get("materials", {})
        audios = materials.get("audios", []) if isinstance(materials, dict) else []
        if not isinstance(audios, list):
            continue
        for audio in audios:
            if not isinstance(audio, dict):
                continue
            raw = str(audio.get("path", ""))
            if "/Cache/music/" not in raw or not raw.lower().endswith(".mp3"):
                continue
            normalized = _normalize_music_path(raw, music_dir)
            if normalized is not None and normalized.exists():
                paths.add(normalized)
    return paths


def _extract_jy_favorite_commercial_tracks(projects_root: Path, music_dir: Path) -> dict[str, Any]:
    if not projects_root.exists() or not projects_root.is_dir():
        return {
            "enabled": False,
            "reason": f"projects_root_not_found:{projects_root}",
            "favorite_total": 0,
            "favorite_commercial_total": 0,
            "resolved_track_total": 0,
            "resolved_tracks": [],
            "unresolved_ids": [],
            "unresolved_preview": [],
        }

    entries: dict[str, dict[str, Any]] = {}
    id_to_paths: dict[str, set[Path]] = {}

    for project_dir in sorted([p for p in projects_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
        key_value_file = project_dir / "key_value.json"
        if not key_value_file.exists():
            continue

        payload = _safe_read_json(key_value_file)
        if not payload:
            continue

        project_music_ids: set[str] = set()
        for raw in payload.values():
            if not isinstance(raw, dict) or not _is_music_entry(raw):
                continue
            music_id = str(raw.get("materialId", "") or "").strip()
            if not music_id:
                continue
            project_music_ids.add(music_id)
            entry = entries.setdefault(
                music_id,
                {
                    "music_id": music_id,
                    "name": str(raw.get("materialName", "") or ""),
                    "favorite": False,
                    "commercial": False,
                    "third_categories": set(),
                    "projects": set(),
                },
            )
            entry["favorite"] = bool(entry["favorite"] or _is_favorite_music(raw))
            entry["commercial"] = bool(entry["commercial"] or _is_commercial_music(raw))
            third = str(raw.get("materialThirdcategory", "") or "").strip()
            if third:
                entry["third_categories"].add(third)
            entry["projects"].add(project_dir.name)

        cache_paths = _collect_cache_music_paths_from_project(project_dir, music_dir)
        # Deterministic mapping heuristic: one project-level music_id + one project-level cache mp3.
        if len(project_music_ids) == 1 and len(cache_paths) == 1:
            only_id = next(iter(project_music_ids))
            id_to_paths.setdefault(only_id, set()).update(cache_paths)

    favorite_entries = [e for e in entries.values() if bool(e.get("favorite"))]
    favorite_commercial = [e for e in favorite_entries if bool(e.get("commercial"))]

    resolved_tracks: list[str] = []
    unresolved_preview: list[dict[str, Any]] = []
    unresolved_ids: list[str] = []

    for item in favorite_commercial:
        mid = str(item.get("music_id", ""))
        mapped = sorted({str(p.resolve()) for p in id_to_paths.get(mid, set()) if p.exists()})
        if mapped:
            resolved_tracks.extend(mapped)
        else:
            unresolved_ids.append(mid)
            unresolved_preview.append(
                {
                    "music_id": mid,
                    "name": str(item.get("name", "") or ""),
                    "projects": sorted(str(x) for x in item.get("projects", set())),
                }
            )

    # Deduplicate stable output
    resolved_tracks = sorted(set(resolved_tracks))

    return {
        "enabled": True,
        "projects_root": str(projects_root),
        "favorite_total": len(favorite_entries),
        "favorite_commercial_total": len(favorite_commercial),
        "resolved_track_total": len(resolved_tracks),
        "resolved_tracks": resolved_tracks,
        "unresolved_ids": unresolved_ids,
        "unresolved_preview": unresolved_preview[:10],
    }


def choose_bgm(
    music_dir: Path,
    history_file: Path,
    mode: str = "auto_tech_from_jy_cache",
    min_music_duration_sec: float = 45.0,
    projects_root: Path | None = None,
    prefer_jy_favorite_commercial: bool = True,
) -> dict[str, Any]:
    now = int(time.time())
    history = _load_json(history_file, {"tracks": {}, "updated_at": 0, "last_pick": "", "recent_picks": []})
    all_tracks = collect_tracks(music_dir)
    if not all_tracks:
        return {
            "ok": False,
            "track_path": "",
            "source": "none",
            "policy": mode,
            "reason": f"no audio files in {music_dir}",
        }

    tracks_meta: dict[str, dict[str, Any]] = history.setdefault("tracks", {})
    for p in all_tracks:
        meta = tracks_meta.setdefault(str(p), {"status": "unknown", "hits": 0, "last_used": 0})
        meta.setdefault("category", detect_track_category(p))

    # Prefer longer clips to avoid selecting SFX-like short assets.
    long_tracks: list[Path] = []
    for p in all_tracks:
        meta = tracks_meta.setdefault(str(p), {"status": "unknown", "hits": 0, "last_used": 0})
        meta.setdefault("category", detect_track_category(p))
        dur = float(meta.get("duration_sec", 0) or 0)
        if dur <= 0:
            dur = probe_duration_sec(p)
            meta["duration_sec"] = round(dur, 3)
        if dur >= min_music_duration_sec:
            long_tracks.append(p)
    pool = long_tracks if long_tracks else all_tracks

    if mode == "music_only":
        music_pool = [p for p in pool if tracks_meta.get(str(p), {}).get("category") == "music"]
        pool = music_pool or pool

    candidates: list[Path]
    source = "random_pool"

    jy_favorites_report: dict[str, Any] = {
        "enabled": False,
        "favorite_total": 0,
        "favorite_commercial_total": 0,
        "resolved_track_total": 0,
    }
    if prefer_jy_favorite_commercial and projects_root is not None:
        jy_favorites_report = _extract_jy_favorite_commercial_tracks(projects_root, music_dir)
        resolved = set(str(Path(p).resolve()) for p in jy_favorites_report.get("resolved_tracks", []))
        if resolved:
            jy_candidates = [p for p in pool if str(p.resolve()) in resolved]
            if jy_candidates:
                candidates = jy_candidates
                source = "jy_favorite_commercial_pool"
            else:
                candidates = []
        else:
            candidates = []
    else:
        candidates = []

    if not candidates:
        if mode == "auto_tech_from_jy_cache":
            music_pool = [p for p in pool if tracks_meta.get(str(p), {}).get("category") == "music"]
            base_pool = music_pool or pool
            tech = [p for p in base_pool if tracks_meta.get(str(p), {}).get("status") == "tech_like"]
            if tech:
                candidates = tech
                source = "tech_like_pool"
            else:
                candidates = [
                    p for p in base_pool if tracks_meta.get(str(p), {}).get("status") != "dislike"
                ]
                if not candidates:
                    candidates = base_pool
                source = "full_pool_fallback"
        else:
            candidates = [p for p in pool if tracks_meta.get(str(p), {}).get("status") != "dislike"]
            if not candidates:
                candidates = pool

    # Rotation rule: avoid immediate repeats and recent picks when possible.
    last_pick = str(history.get("last_pick", "") or "").strip()
    recent_raw = history.get("recent_picks", [])
    recent_picks = [str(x) for x in recent_raw] if isinstance(recent_raw, list) else []
    if last_pick and len(candidates) > 1:
        filtered = [p for p in candidates if str(p) != last_pick]
        if filtered:
            candidates = filtered
            source += "_no_repeat"

    recent_window = min(3, len(candidates) - 1) if len(candidates) > 1 else 0
    if recent_window > 0 and recent_picks:
        avoid_recent = set(recent_picks[-recent_window:])
        filtered = [p for p in candidates if str(p) not in avoid_recent]
        if filtered:
            candidates = filtered
            source += "_rotated"

    chosen = random.choice(candidates)
    key = str(chosen)
    meta = tracks_meta.setdefault(key, {"status": "unknown", "hits": 0, "last_used": 0})
    meta["hits"] = int(meta.get("hits", 0)) + 1
    meta["last_used"] = now
    history["last_pick"] = key
    recent_picks.append(key)
    history["recent_picks"] = recent_picks[-20:]
    history["updated_at"] = now
    _save_json(history_file, history)

    return {
        "ok": True,
        "track_path": key,
        "source": source,
        "policy": mode,
        "history_file": str(history_file),
        "status": meta.get("status", "unknown"),
        "category": meta.get("category", "unknown"),
        "duration_sec": float(meta.get("duration_sec", 0) or 0),
        "min_music_duration_sec": min_music_duration_sec,
        "jy_favorites": {
            "enabled": bool(jy_favorites_report.get("enabled", False)),
            "favorite_total": int(jy_favorites_report.get("favorite_total", 0) or 0),
            "favorite_commercial_total": int(jy_favorites_report.get("favorite_commercial_total", 0) or 0),
            "resolved_track_total": int(jy_favorites_report.get("resolved_track_total", 0) or 0),
            "unresolved_ids": list(jy_favorites_report.get("unresolved_ids", [])),
            "unresolved_preview": list(jy_favorites_report.get("unresolved_preview", [])),
        },
    }


def update_feedback(history_file: Path, track_path: Path, feedback: str) -> dict[str, Any]:
    history = _load_json(history_file, {"tracks": {}, "updated_at": 0, "last_pick": ""})
    key = str(track_path.resolve())
    tracks_meta: dict[str, dict[str, Any]] = history.setdefault("tracks", {})
    meta = tracks_meta.setdefault(key, {"status": "unknown", "hits": 0, "last_used": 0})

    fb = feedback.strip().lower()
    if fb in {"音效", "sfx"}:
        meta["category"] = "sfx"
    elif fb in {"音乐", "music"}:
        meta["category"] = "music"

    if fb in {"tech_like", "like", "ok", "good", "可以", "加入科技池"}:
        status = "tech_like"
    elif fb in {"dislike", "bad", "no", "不行", "拉黑"}:
        status = "dislike"
    else:
        status = "unknown"

    meta["status"] = status
    meta["last_feedback"] = feedback
    meta["last_feedback_at"] = int(time.time())
    history["updated_at"] = int(time.time())
    _save_json(history_file, history)
    return {
        "ok": True,
        "track_path": key,
        "status": status,
        "category": meta.get("category", "unknown"),
        "history_file": str(history_file),
    }


def cli() -> None:
    cfg = load_pipeline_config()
    parser = argparse.ArgumentParser(description="BGM selector from JianYing cache with learning history")
    parser.add_argument("--music-dir", default=str(cfg.jy_cache_music_dir))
    parser.add_argument(
        "--history-file",
        default=str(cfg.voice_profile_path.parent / "bgm_history.json"),
    )
    parser.add_argument("--jy-projects-root", default=str(cfg.jy_projects_root))
    parser.add_argument(
        "--disable-jy-favorite-commercial",
        action="store_true",
        help="Disable priority picking from JianYing favorite+commercial tracks",
    )
    sub = parser.add_subparsers(dest="action", required=True)

    choose = sub.add_parser("choose")
    choose.add_argument("--bgm-mode", default="auto_tech_from_jy_cache")
    choose.add_argument("--min-music-duration-sec", type=float, default=45.0)

    fb = sub.add_parser("feedback")
    fb.add_argument("--track-path", required=True)
    fb.add_argument("--feedback", required=True)

    args = parser.parse_args()
    music_dir = Path(args.music_dir).expanduser().resolve()
    history_file = Path(args.history_file).expanduser().resolve()

    if args.action == "choose":
        report = choose_bgm(
            music_dir=music_dir,
            history_file=history_file,
            mode=args.bgm_mode,
            min_music_duration_sec=args.min_music_duration_sec,
            projects_root=Path(args.jy_projects_root).expanduser().resolve(),
            prefer_jy_favorite_commercial=not bool(args.disable_jy_favorite_commercial),
        )
    else:
        report = update_feedback(
            history_file=history_file,
            track_path=Path(args.track_path).expanduser().resolve(),
            feedback=args.feedback,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
