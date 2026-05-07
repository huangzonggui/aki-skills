#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import shutil
from pathlib import Path
from typing import Any


STILL_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _resolve_binary(name: str) -> str:
    candidate = shutil.which(name)
    if candidate:
        return candidate
    common = {
        "ffmpeg": ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"],
        "ffprobe": ["/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe"],
    }
    for raw in common.get(name, []):
        path = Path(raw)
        if path.exists():
            return str(path)
    return name


FFMPEG_BIN = _resolve_binary("ffmpeg")
FFPROBE_BIN = _resolve_binary("ffprobe")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_payload_to_all(draft_dir: Path, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    for name in ("draft_content.json", "draft_info.json", "draft_info.json.bak"):
        (draft_dir / name).write_text(raw, encoding="utf-8")


def _probe_video(path: Path) -> dict[str, int]:
    raw = subprocess.check_output(
        [
            FFPROBE_BIN,
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


def _even(value: int) -> int:
    number = max(2, int(value))
    return number if number % 2 == 0 else number + 1


def _default_bbox(image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = image_size
    return (0, 0, width, height)


def detect_content_bbox(image_path: Path, threshold: int = 245) -> tuple[int, int, int, int]:
    try:
        from PIL import Image
    except Exception:
        return _default_bbox((1, 1))

    with Image.open(image_path) as img:
        rgba = img.convert("RGBA")
        width, height = rgba.size
        pixels = rgba.load()
        min_x = width
        min_y = height
        max_x = -1
        max_y = -1

        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                if a <= 8:
                    continue
                if r < threshold or g < threshold or b < threshold:
                    if x < min_x:
                        min_x = x
                    if y < min_y:
                        min_y = y
                    if x > max_x:
                        max_x = x
                    if y > max_y:
                        max_y = y

        if max_x < min_x or max_y < min_y:
            return _default_bbox((width, height))
        return (min_x, min_y, max_x + 1, max_y + 1)


def plan_foreground_layout(
    image_size: tuple[int, int],
    bbox: tuple[int, int, int, int],
    target_size: tuple[int, int],
) -> dict[str, Any]:
    src_w, src_h = image_size
    target_w, target_h = target_size
    if src_w <= 0 or src_h <= 0:
        raise ValueError("invalid source image size")

    scale = min(target_w / float(src_w), target_h / float(src_h))
    fg_w = min(target_w, _even(round(src_w * scale)))
    fg_h = min(target_h, _even(round(src_h * scale)))

    default_x = max(0, int(round((target_w - fg_w) / 2.0)))
    default_y = max(0, int(round((target_h - fg_h) / 2.0)))

    left, top, right, bottom = bbox
    bbox_cx = ((left + right) / 2.0) * scale
    bbox_cy = ((top + bottom) / 2.0) * scale
    desired_x = int(round((target_w / 2.0) - bbox_cx))
    desired_y = int(round((target_h / 2.0) - bbox_cy))

    max_x = max(0, target_w - fg_w)
    max_y = max(0, target_h - fg_h)
    offset_x = min(max(desired_x, 0), max_x)
    offset_y = min(max(desired_y, 0), max_y)

    return {
        "scale": round(scale, 6),
        "foreground_size": (fg_w, fg_h),
        "foreground_offset": (offset_x, offset_y),
        "default_offset": (default_x, default_y),
        "bbox_center_scaled": (round(bbox_cx, 3), round(bbox_cy, 3)),
        "canvas_margins": {
            "left": offset_x,
            "right": max(0, target_w - fg_w - offset_x),
            "top": offset_y,
            "bottom": max(0, target_h - fg_h - offset_y),
        },
    }


def _probe_image_size(image_path: Path) -> tuple[int, int]:
    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError("Pillow is required for still image layout planning") from exc
    with Image.open(image_path) as img:
        return img.size


def _build_filter_complex(
    *,
    target_size: tuple[int, int],
    foreground_size: tuple[int, int],
    foreground_offset: tuple[int, int],
    image_fit_mode: str,
    bg_extension_blur: float,
) -> str:
    target_w, target_h = target_size
    fg_w, fg_h = foreground_size
    offset_x, offset_y = foreground_offset
    blur_radius = max(12, int(round(18 + (max(0.0, min(1.0, bg_extension_blur)) * 40))))

    foreground = f"[0:v]scale={fg_w}:{fg_h}:flags=lanczos[fg]"
    if image_fit_mode == "contain_with_bg_extension":
        background = (
            f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h},boxblur={blur_radius}:1[bg]"
        )
    else:
        background = f"color=c=white:s={target_w}x{target_h}[bg]"
    overlay = f"[bg][fg]overlay={offset_x}:{offset_y},format=yuv420p,setsar=1[v]"
    return ";".join([background, foreground, overlay])


def _render_still_clip(
    image_path: Path,
    output_path: Path,
    duration_sec: float,
    fps: int,
    *,
    image_fit_mode: str,
    content_bbox_threshold: int,
    bg_extension_blur: float,
    target_size: tuple[int, int],
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image_size = _probe_image_size(image_path)
    bbox = detect_content_bbox(image_path, threshold=content_bbox_threshold)
    if bbox == (0, 0, 1, 1):
        bbox = _default_bbox(image_size)

    use_bbox = image_fit_mode in {"contain_center_by_content", "contain_with_bg_extension"}
    layout = plan_foreground_layout(
        image_size=image_size,
        bbox=(bbox if use_bbox else _default_bbox(image_size)),
        target_size=target_size,
    )
    filter_complex = _build_filter_complex(
        target_size=target_size,
        foreground_size=layout["foreground_size"],
        foreground_offset=layout["foreground_offset"],
        image_fit_mode=image_fit_mode,
        bg_extension_blur=bg_extension_blur,
    )
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-t",
        f"{duration_sec:.3f}",
        "-r",
        str(fps),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
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
    video_meta = _probe_video(output_path)
    return {
        **video_meta,
        "image_size": image_size,
        "content_bbox": bbox,
        "layout": layout,
        "image_fit_mode": image_fit_mode,
        "bg_extension_blur": bg_extension_blur,
        "target_size": target_size,
        "filter_complex": filter_complex,
    }


def repair_draft(
    draft_dir: Path,
    pad_sec: float,
    min_sec: float,
    fps: int,
    *,
    image_fit_mode: str,
    content_bbox_threshold: int,
    bg_extension_blur: float,
    target_size: tuple[int, int],
) -> dict[str, Any]:
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
        clip_meta = _render_still_clip(
            source_path,
            clip_path,
            duration_sec=duration_sec,
            fps=fps,
            image_fit_mode=image_fit_mode,
            content_bbox_threshold=content_bbox_threshold,
            bg_extension_blur=bg_extension_blur,
            target_size=target_size,
        )
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
                "image_size": list(clip_meta["image_size"]),
                "content_bbox": list(clip_meta["content_bbox"]),
                "layout": clip_meta["layout"],
                "image_fit_mode": clip_meta["image_fit_mode"],
                "bg_extension_blur": clip_meta["bg_extension_blur"],
            }
        )

    _write_payload_to_all(draft_dir, data)
    return {
        "draft_dir": str(draft_dir),
        "repaired_count": len(repaired),
        "repaired": repaired,
        "skipped_missing_sources": skipped,
        "still_clip_dir": str(local_clip_dir),
        "image_fit_mode": image_fit_mode,
        "content_bbox_threshold": content_bbox_threshold,
        "bg_extension_blur": bg_extension_blur,
        "target_size": list(target_size),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair JianYing drafts whose still images were mis-ingested as black-screen clips")
    parser.add_argument("--draft-dir", required=True)
    parser.add_argument("--pad-sec", type=float, default=0.8)
    parser.add_argument("--min-sec", type=float, default=6.0)
    parser.add_argument("--fps", type=int, default=25)
    parser.add_argument(
        "--image-fit-mode",
        default="contain_with_bg_extension",
        choices=["contain_preserve", "contain_center_by_content", "contain_with_bg_extension"],
    )
    parser.add_argument("--content-bbox-threshold", type=int, default=245)
    parser.add_argument("--bg-extension-blur", type=float, default=0.75)
    parser.add_argument("--target-width", type=int, default=1440)
    parser.add_argument("--target-height", type=int, default=2560)
    parser.add_argument("--json-report", default="")
    args = parser.parse_args()

    draft_dir = Path(args.draft_dir).expanduser().resolve()
    report = repair_draft(
        draft_dir=draft_dir,
        pad_sec=args.pad_sec,
        min_sec=args.min_sec,
        fps=args.fps,
        image_fit_mode=args.image_fit_mode,
        content_bbox_threshold=args.content_bbox_threshold,
        bg_extension_blur=args.bg_extension_blur,
        target_size=(args.target_width, args.target_height),
    )
    if args.json_report:
        report_path = Path(args.json_report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
