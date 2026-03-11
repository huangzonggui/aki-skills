#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from pipeline_config import load_pipeline_config


@dataclass
class VoiceProfile:
    voice_name: str
    provider: str = "siliconflow"
    model: str = "IndexTeam/IndexTTS-2"
    voice_uri: str = ""
    ref_audio_path: str = ""
    default_speed: float = 1.0
    notes: str = ""
    updated_at: int = 0


BUILTIN_PROFILES = {
    "日常松弛男": VoiceProfile(
        voice_name="日常松弛男",
        provider="siliconflow",
        model="IndexTeam/IndexTTS-2",
        ref_audio_path="",
        default_speed=1.3,
        notes="default profile for Aki local pipeline",
    )
}


def _now_ts() -> int:
    return int(time.time())


def _load_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"profiles": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"profiles": []}
    if isinstance(data, list):
        return {"profiles": data}
    if not isinstance(data, dict):
        return {"profiles": []}
    if "profiles" not in data or not isinstance(data["profiles"], list):
        data["profiles"] = []
    return data


def _save_raw(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _profile_from_obj(obj: dict[str, Any]) -> VoiceProfile:
    return VoiceProfile(
        voice_name=str(obj.get("voice_name", "")).strip(),
        provider=str(obj.get("provider", "siliconflow")).strip() or "siliconflow",
        model=str(obj.get("model", "IndexTeam/IndexTTS-2")).strip() or "IndexTeam/IndexTTS-2",
        voice_uri=str(obj.get("voice_uri", "")).strip(),
        ref_audio_path=str(obj.get("ref_audio_path", "")).strip(),
        default_speed=float(obj.get("default_speed", 1.0)),
        notes=str(obj.get("notes", "")).strip(),
        updated_at=int(obj.get("updated_at", 0) or 0),
    )


def _profile_to_obj(p: VoiceProfile) -> dict[str, Any]:
    d = asdict(p)
    d["updated_at"] = _now_ts()
    return d


def load_profiles(profile_path: Path) -> dict[str, VoiceProfile]:
    raw = _load_raw(profile_path)
    out: dict[str, VoiceProfile] = {}
    for obj in raw.get("profiles", []):
        if not isinstance(obj, dict):
            continue
        p = _profile_from_obj(obj)
        if p.voice_name:
            out[p.voice_name] = p
    for name, builtin in BUILTIN_PROFILES.items():
        if name not in out:
            out[name] = builtin
            continue
        curr = out[name]
        if not curr.provider:
            curr.provider = builtin.provider
        if not curr.model:
            curr.model = builtin.model
        if not curr.ref_audio_path:
            curr.ref_audio_path = builtin.ref_audio_path
        if not curr.default_speed:
            curr.default_speed = builtin.default_speed
    return out


def save_profiles(profile_path: Path, profiles: dict[str, VoiceProfile]) -> None:
    serial = [_profile_to_obj(profiles[k]) for k in sorted(profiles.keys())]
    payload = {"profiles": serial, "updated_at": _now_ts()}
    _save_raw(profile_path, payload)


def get_profile(profile_path: Path, voice_name: str) -> VoiceProfile:
    profiles = load_profiles(profile_path)
    if voice_name in profiles:
        return profiles[voice_name]
    return VoiceProfile(voice_name=voice_name)


def upsert_profile(
    profile_path: Path,
    voice_name: str,
    provider: str,
    model: str,
    default_speed: float | None,
    ref_audio_path: str = "",
    voice_uri: str = "",
    notes: str = "",
) -> VoiceProfile:
    profiles = load_profiles(profile_path)
    curr = profiles.get(voice_name, VoiceProfile(voice_name=voice_name))
    curr.provider = provider or curr.provider
    curr.model = model or curr.model
    if default_speed is not None and float(default_speed) > 0:
        curr.default_speed = float(default_speed)
    if ref_audio_path:
        curr.ref_audio_path = ref_audio_path
    if voice_uri:
        curr.voice_uri = voice_uri
    if notes:
        curr.notes = notes
    curr.updated_at = _now_ts()
    profiles[voice_name] = curr
    save_profiles(profile_path, profiles)
    return curr


def update_voice_uri(profile_path: Path, voice_name: str, voice_uri: str) -> VoiceProfile:
    profiles = load_profiles(profile_path)
    curr = profiles.get(voice_name, VoiceProfile(voice_name=voice_name))
    curr.voice_uri = voice_uri.strip()
    curr.updated_at = _now_ts()
    profiles[voice_name] = curr
    save_profiles(profile_path, profiles)
    return curr


def ref_audio_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def cli() -> None:
    cfg = load_pipeline_config()
    parser = argparse.ArgumentParser(description="Voice profile registry for aki-image-article-video")
    parser.add_argument(
        "--profile-file",
        default=str(cfg.voice_profile_path),
        help="voice profile json file path",
    )
    sub = parser.add_subparsers(dest="action", required=True)

    reg = sub.add_parser("register")
    reg.add_argument("--voice-name", required=True)
    reg.add_argument("--provider", default="siliconflow")
    reg.add_argument("--model", default="IndexTeam/IndexTTS-2")
    reg.add_argument("--default-speed", type=float, default=1.0)
    reg.add_argument("--ref-audio-path", default="")
    reg.add_argument("--voice-uri", default="")
    reg.add_argument("--notes", default="")

    get = sub.add_parser("get")
    get.add_argument("--voice-name", required=True)

    set_uri = sub.add_parser("set-uri")
    set_uri.add_argument("--voice-name", required=True)
    set_uri.add_argument("--voice-uri", required=True)

    sub.add_parser("list")

    args = parser.parse_args()
    profile_path = Path(args.profile_file).expanduser().resolve()

    if args.action == "register":
        p = upsert_profile(
            profile_path=profile_path,
            voice_name=args.voice_name,
            provider=args.provider,
            model=args.model,
            default_speed=args.default_speed,
            ref_audio_path=args.ref_audio_path,
            voice_uri=args.voice_uri,
            notes=args.notes,
        )
        print(json.dumps({"ok": True, "profile": asdict(p)}, ensure_ascii=False, indent=2))
        return

    if args.action == "get":
        p = get_profile(profile_path, args.voice_name)
        print(json.dumps({"ok": True, "profile": asdict(p)}, ensure_ascii=False, indent=2))
        return

    if args.action == "set-uri":
        p = update_voice_uri(profile_path, args.voice_name, args.voice_uri)
        print(json.dumps({"ok": True, "profile": asdict(p)}, ensure_ascii=False, indent=2))
        return

    profiles = load_profiles(profile_path)
    print(
        json.dumps(
            {"ok": True, "count": len(profiles), "voices": sorted(profiles.keys())},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    cli()
