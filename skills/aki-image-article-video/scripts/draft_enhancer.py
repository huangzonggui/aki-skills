#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import uuid
from pathlib import Path
from typing import Any


SHRINK_IN_ANIMATION = {
    "resource_id": "6798332584276267527",
    "category_name": "入场",
    "id": "624755",
    "material_type": "video",
    "path": "",
    "platform": "all",
    "request_id": "",
    "category_id": "ruchang",
    "duration": 500000,
    "name": "缩小",
    "panel": "video",
    "start": 0,
    "type": "in",
    "anim_adjust_params": None,
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_payload_to_all(draft_dir: Path, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    for name in ("draft_content.json", "draft_info.json", "draft_info.json.bak"):
        (draft_dir / name).write_text(raw, encoding="utf-8")


def probe_duration_us(audio_path: Path) -> int:
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
    sec = float(out)
    return max(1, int(round(sec * 1_000_000)))


def _db_to_gain(db: float) -> float:
    return max(0.0, 10 ** (db / 20.0))


def _iter_video_segments(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for track in data.get("tracks", []):
        if track.get("type") != "video":
            continue
        out.extend(track.get("segments", []) or [])
    return out


def apply_light_zoom(data: dict[str, Any], zoom_hi: float = 1.03, zoom_lo: float = 1.0) -> dict[str, Any]:
    materials = data.setdefault("materials", {})
    mat_animations = materials.setdefault("material_animations", [])
    video_segments = _iter_video_segments(data)

    changed = 0
    anim_added = 0
    for idx, seg in enumerate(video_segments):
        clip = seg.setdefault("clip", {})
        scale = clip.setdefault("scale", {"x": 1.0, "y": 1.0})
        target = zoom_hi if idx % 2 == 0 else zoom_lo
        scale["x"] = target
        scale["y"] = target
        changed += 1

        anim_id = uuid.uuid4().hex
        mat_animations.append(
            {
                "animations": [dict(SHRINK_IN_ANIMATION)],
                "id": anim_id,
                "multi_language_current": "none",
                "type": "sticker_animation",
            }
        )
        refs = seg.setdefault("extra_material_refs", [])
        refs.append(anim_id)
        anim_added += 1

    return {"changed_segments": changed, "added_animations": anim_added}


def _extract_speech_regions(data: dict[str, Any]) -> list[tuple[int, int]]:
    raw: list[tuple[int, int]] = []
    for track in data.get("tracks", []):
        if track.get("type") != "text":
            continue
        for seg in track.get("segments", []) or []:
            tr = seg.get("target_timerange") or {}
            start = int(tr.get("start", 0) or 0)
            dur = int(tr.get("duration", 0) or 0)
            if dur > 0:
                raw.append((start, start + dur))
    if not raw:
        return []
    raw.sort(key=lambda x: x[0])
    merged = [raw[0]]
    for st, ed in raw[1:]:
        last_st, last_ed = merged[-1]
        if st <= last_ed:
            merged[-1] = (last_st, max(last_ed, ed))
        else:
            merged.append((st, ed))
    return merged


def _build_regions(total_us: int, speech: list[tuple[int, int]], silence_gap_us: int) -> list[tuple[int, int, bool]]:
    if total_us <= 0:
        return []
    if not speech:
        return [(0, total_us, False)]

    regions: list[tuple[int, int, bool]] = []
    cursor = 0
    for st, ed in speech:
        st = max(0, st)
        ed = min(total_us, ed)
        if st > cursor:
            gap = st - cursor
            is_speech = gap <= silence_gap_us
            regions.append((cursor, st, is_speech))
        if ed > st:
            regions.append((st, ed, True))
        cursor = max(cursor, ed)
    if cursor < total_us:
        gap = total_us - cursor
        is_speech = gap <= silence_gap_us
        regions.append((cursor, total_us, is_speech))
    return [r for r in regions if r[1] > r[0]]


def _make_loop_segments(
    material_id: str,
    total_us: int,
    source_duration_us: int,
    regions: list[tuple[int, int, bool]],
    speech_gain: float,
    gap_gain: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if source_duration_us <= 0:
        return out

    for start_us, end_us, is_speech in regions:
        remain = end_us - start_us
        t_cursor = start_us
        s_cursor = start_us % source_duration_us
        vol = speech_gain if is_speech else gap_gain
        while remain > 0:
            chunk = min(remain, source_duration_us - s_cursor)
            out.append(
                {
                    "id": uuid.uuid4().hex,
                    "material_id": material_id,
                    "target_timerange": {"start": t_cursor, "duration": chunk},
                    "source_timerange": {"start": s_cursor, "duration": chunk},
                    "volume": vol,
                    "speed": 1,
                    "extra_material_refs": [],
                    "visible": True,
                    "track_attribute": 0,
                }
            )
            t_cursor += chunk
            remain -= chunk
            s_cursor = (s_cursor + chunk) % source_duration_us
    return out


def add_bgm_track(
    data: dict[str, Any],
    bgm_path: Path,
    total_us: int,
    speech_follow: bool = False,
    speech_db: float = -23.0,
    gap_db: float = -20.0,
    silence_gap_sec: float = 1.2,
) -> dict[str, Any]:
    materials = data.setdefault("materials", {})
    audios = materials.setdefault("audios", [])
    source_duration_us = probe_duration_us(bgm_path)

    material_id = uuid.uuid4().hex
    audios.append(
        {
            "id": material_id,
            "path": str(bgm_path),
            "type": "extract_music",
            "duration": source_duration_us,
            "name": bgm_path.name,
            "material_name": bgm_path.name,
            "local_material_id": "",
            "music_id": "",
            "check_flag": 1,
            "source_platform": 0,
            "category_name": "local",
            "category_id": "",
            "copyright_limit_type": "none",
            "wave_points": [],
        }
    )

    tracks = data.setdefault("tracks", [])
    bgm_track = None
    for t in tracks:
        if t.get("type") == "audio" and str(t.get("name", "")).lower() == "bgmtrack":
            bgm_track = t
            break
    if bgm_track is None:
        bgm_track = {
            "attribute": 0,
            "flag": 0,
            "id": str(uuid.uuid4()).upper(),
            "is_default_name": False,
            "name": "BGMTrack",
            "segments": [],
            "type": "audio",
        }
        tracks.append(bgm_track)

    regions: list[tuple[int, int, bool]]
    if speech_follow:
        speech = _extract_speech_regions(data)
        regions = _build_regions(total_us, speech, int(silence_gap_sec * 1_000_000))
    else:
        regions = [(0, total_us, True)]

    segments = _make_loop_segments(
        material_id=material_id,
        total_us=total_us,
        source_duration_us=source_duration_us,
        regions=regions,
        speech_gain=_db_to_gain(speech_db),
        gap_gain=_db_to_gain(gap_db),
    )
    bgm_track["segments"] = segments
    return {
        "bgm_material_id": material_id,
        "bgm_segments": len(segments),
        "speech_follow": speech_follow,
        "speech_db": speech_db,
        "gap_db": gap_db,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Enhance JianYing draft with light animation and BGM track")
    parser.add_argument("--draft-dir", required=True)
    parser.add_argument("--animation-preset", default="flip_zoom", choices=["none", "flip_zoom"])
    parser.add_argument("--bgm-path", default="")
    parser.add_argument("--enable-bgm-speech-follow", action="store_true")
    parser.add_argument("--disable-bgm-speech-follow", action="store_true")
    parser.add_argument("--bgm-speech-db", type=float, default=-23.0)
    parser.add_argument("--bgm-gap-db", type=float, default=-20.0)
    parser.add_argument("--silence-gap-sec", type=float, default=1.2)
    parser.add_argument("--json-report", default="")
    args = parser.parse_args()

    draft_dir = Path(args.draft_dir).expanduser().resolve()
    content_path = draft_dir / "draft_content.json"
    if not content_path.exists():
        raise FileNotFoundError(f"draft_content.json not found: {content_path}")
    data = _read_json(content_path)
    total_us = int(data.get("duration", 0) or 0)
    report: dict[str, Any] = {
        "draft_dir": str(draft_dir),
        "animation": {},
        "bgm": {},
        "warnings": [],
    }

    if args.animation_preset == "flip_zoom":
        report["animation"] = apply_light_zoom(data)

    if args.bgm_path:
        bgm_path = Path(args.bgm_path).expanduser().resolve()
        if not bgm_path.exists():
            report["warnings"].append(f"BGM file missing: {bgm_path}")
        else:
            report["bgm"] = add_bgm_track(
                data=data,
                bgm_path=bgm_path,
                total_us=total_us,
                speech_follow=(
                    args.enable_bgm_speech_follow and not args.disable_bgm_speech_follow
                ),
                speech_db=args.bgm_speech_db,
                gap_db=args.bgm_gap_db,
                silence_gap_sec=args.silence_gap_sec,
            )

    _write_payload_to_all(draft_dir, data)

    if args.json_report:
        report_path = Path(args.json_report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
