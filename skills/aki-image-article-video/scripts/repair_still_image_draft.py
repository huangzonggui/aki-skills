#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


STILL_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_payload_to_all(draft_dir: Path, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    for name in ("draft_content.json", "draft_info.json", "draft_info.json.bak"):
        (draft_dir / name).write_text(raw, encoding="utf-8")


def _probe_video(path: Path) -> dict[str, int]:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,duration",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    data = json.loads(raw)
    stream = ((data.get("streams") or [{}])[0]) if isinstance(data, dict) else {}
    duration_sec = float(stream.get("duration") or 0.0)
    return {
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "duration_us": max(1, int(round(duration_sec * 1_000_000))),
    }


def _required_material_durations_us(data: dict[str, Any]) -> dict[str, int]:
    durations: dict[str, int] = {}
    for track in data.get("tracks", []):
        if track.get("type") != "video":
            continue
        for seg in track.get("segments", []) or []:
            material_id = str(seg.get("material_id") or "").strip()
            if not material_id:
                continue
            target = int(((seg.get("target_timerange") or {}).get("duration")) or 0)
            source = int(((seg.get("source_timerange") or {}).get("duration")) or 0)
            need = max(target, source)
            if need > durations.get(material_id, 0):
                durations[material_id] = need
    return durations


def _render_still_clip(image_path: Path, output_path: Path, duration_sec: float, fps: int) -> dict[str, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-t",
        f"{duration_sec:.3f}",
        "-r",
        str(fps),
        "-vf",
        "scale=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p,setsar=1",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return _probe_video(output_path)


def repair_draft(draft_dir: Path, pad_sec: float, min_sec: float, fps: int) -> dict[str, Any]:
    content_path = draft_dir / "draft_content.json"
    if not content_path.exists():
        raise FileNotFoundError(f"draft_content.json not found: {content_path}")

    data = _read_json(content_path)
    materials = data.setdefault("materials", {})
    videos = materials.setdefault("videos", [])
    required_durations = _required_material_durations_us(data)
    local_clip_dir = draft_dir / "local_assets" / "still_clips"
    local_clip_dir.mkdir(parents=True, exist_ok=True)

    repaired: list[dict[str, Any]] = []
    skipped: list[str] = []
    for index, material in enumerate(videos):
        source_path = Path(str(material.get("path") or "")).expanduser()
        if source_path.suffix.lower() not in STILL_IMAGE_SUFFIXES:
            continue
        if not source_path.exists():
            skipped.append(str(source_path))
            continue
        material_id = str(material.get("id") or material.get("material_id") or "").strip()
        required_us = required_durations.get(material_id, 0)
        duration_sec = max(min_sec, (required_us / 1_000_000.0) + pad_sec)
        clip_path = local_clip_dir / f"{index + 1:02d}_{source_path.stem}.mp4"
        clip_meta = _render_still_clip(source_path, clip_path, duration_sec=duration_sec, fps=fps)
        material["path"] = str(clip_path)
        material["material_name"] = clip_path.name
        material["type"] = "video"
        material["width"] = clip_meta["width"]
        material["height"] = clip_meta["height"]
        material["duration"] = clip_meta["duration_us"]
        repaired.append(
            {
                "material_id": material_id,
                "from": str(source_path),
                "to": str(clip_path),
                "duration_sec": round(clip_meta["duration_us"] / 1_000_000.0, 3),
                "required_duration_sec": round(required_us / 1_000_000.0, 3),
                "size": [clip_meta["width"], clip_meta["height"]],
            }
        )

    _write_payload_to_all(draft_dir, data)
    return {
        "draft_dir": str(draft_dir),
        "repaired_count": len(repaired),
        "repaired": repaired,
        "skipped_missing_sources": skipped,
        "still_clip_dir": str(local_clip_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair JianYing drafts whose still images were mis-ingested as black-screen clips")
    parser.add_argument("--draft-dir", required=True)
    parser.add_argument("--pad-sec", type=float, default=0.8)
    parser.add_argument("--min-sec", type=float, default=6.0)
    parser.add_argument("--fps", type=int, default=25)
    parser.add_argument("--json-report", default="")
    args = parser.parse_args()

    draft_dir = Path(args.draft_dir).expanduser().resolve()
    report = repair_draft(draft_dir=draft_dir, pad_sec=args.pad_sec, min_sec=args.min_sec, fps=args.fps)
    if args.json_report:
        report_path = Path(args.json_report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
