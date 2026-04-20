#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from state import DONE, FAILED, RUNNING, set_artifact, set_step
from topic_layout import DEFAULT_RENDER_PLATFORMS_BY_MODE, IMAGE_PLATFORMS, VIDEO_PLATFORM_CONFIG, resolve_layout
from utils import clear_directory, copy_selected_images, load_json_file, run, run_checked


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(os.getenv("AKI_SKILLS_REPO_ROOT", "")).expanduser().resolve() if os.getenv("AKI_SKILLS_REPO_ROOT") else SCRIPT_DIR.parents[2]
SHARED_DIR = REPO_ROOT / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from aki_runtime import (  # noqa: E402
    default_auto_exporter_path,
    default_jianying_projects_root,
    default_jianying_sync_root,
    skill_path,
)


VIDEO_PIPELINE = skill_path("aki-image-article-video", "scripts", "nl_entrypoint.py", repo_root_path=REPO_ROOT)
AUTO_EXPORTER = default_auto_exporter_path()


def _run_cmd(cmd: list[str]) -> dict:
    cp = run(cmd)
    return {
        "command": cmd,
        "exit_code": cp.returncode,
        "stdout": cp.stdout.strip(),
        "stderr": cp.stderr.strip(),
        "ok": cp.returncode == 0,
    }


def _extract_json_tail(text: str) -> dict:
    text = text.strip()
    if not text:
        return {}
    start = text.rfind("\n{")
    if start == -1 and text.startswith("{"):
        start = 0
    if start == -1:
        return {}
    blob = text[start:].strip()
    try:
        return json.loads(blob)
    except Exception:
        return {}


def _safe_draft_name(raw: str, suffix: str = "_video", max_len: int = 48) -> str:
    stem = re.sub(r"[^\w\-一-龥]+", "_", (raw or "").strip())
    stem = re.sub(r"_+", "_", stem).strip("_")
    if not stem:
        stem = "topic"
    cap = max(8, max_len - len(suffix))
    stem = stem[:cap].rstrip("_")
    return f"{stem}{suffix}"


def _parse_platforms(raw: str, mode: str) -> list[str]:
    value = (raw or "auto").strip().lower()
    if value in {"", "auto"}:
        return list(DEFAULT_RENDER_PLATFORMS_BY_MODE.get(mode, DEFAULT_RENDER_PLATFORMS_BY_MODE["prod"]))
    if value == "all":
        return list(IMAGE_PLATFORMS)
    items = [item.strip() for item in value.split(",") if item.strip()]
    invalid = [item for item in items if item not in IMAGE_PLATFORMS]
    if invalid:
        raise ValueError(f"Unknown platform(s): {', '.join(invalid)}")
    return items


def _parse_markdown_script_sections(path: Path) -> list[str]:
    if not path.exists():
        return []
    sections: list[str] = []
    body_lines: list[str] = []
    in_section = False
    in_body = False
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            if in_section:
                text = "\n".join(body_lines).strip()
                if text:
                    sections.append(text)
            in_section = True
            in_body = False
            body_lines = []
            continue
        if not in_section:
            continue
        if not in_body:
            if not line.strip():
                in_body = True
            continue
        body_lines.append(line)
    if in_section:
        text = "\n".join(body_lines).strip()
        if text:
            sections.append(text)
    return sections


def _parse_plain_script_sections(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return []
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


def _load_script_override(layout, platform: str, expected_count: int) -> tuple[list[str], str] | None:
    candidates = [
        layout.video_voice_tts_script_path(platform),
        layout.video_voice_script_path(platform),
    ]
    existing = [path for path in candidates if path.exists()]
    existing.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for path in existing:
        sections = _parse_markdown_script_sections(path)
        if len(sections) == expected_count and all(item.strip() for item in sections):
            return sections, str(path)
    return None


def _select_stage_script_text(
    stage_script: Path,
    script_override: tuple[list[str], str] | None,
) -> tuple[str | None, str | None]:
    cached_text = ""
    cached_mtime = -1.0
    if stage_script.exists():
        cached_text = stage_script.read_text(encoding="utf-8", errors="ignore").strip()
        cached_mtime = stage_script.stat().st_mtime

    if script_override:
        override_lines, override_source = script_override
        override_path = Path(override_source)
        override_mtime = override_path.stat().st_mtime if override_path.exists() else float("inf")
        if override_mtime > cached_mtime or not cached_text:
            return "\n\n".join(override_lines).strip(), override_source

    if cached_text:
        return cached_text, str(stage_script)
    return None, None


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _choose_export_strategy(force_export: bool, platform_name: str | None = None) -> str:
    current = (platform_name or sys.platform).lower()
    if current.startswith("win"):
        return "native_auto_export"
    if force_export and _ffmpeg_available():
        return "ffmpeg_fallback"
    if force_export:
        return "unsupported_force_export"
    return "skip_unsupported"


def _extract_still_clip_paths(parsed: dict, expected_count: int) -> list[Path]:
    repaired = (parsed.get("draft_asset_repair") or {}).get("repaired") or []
    clips: list[Path] = []
    for item in repaired:
        target = Path(str(item.get("to") or "")).expanduser().resolve()
        if target.exists():
            clips.append(target)
    clips.sort(key=lambda path: path.name.lower())
    if len(clips) >= expected_count:
        return clips[:expected_count]
    return []


def _allocate_segment_durations(script_sections: list[str], total_duration: float, segment_count: int) -> list[float]:
    if segment_count <= 0:
        return []
    usable_total = max(float(total_duration), segment_count * 0.8)
    cleaned = script_sections[:segment_count]
    weights = [
        max(1, len(re.sub(r"\s+", "", section)))
        for section in cleaned
    ]
    if len(weights) < segment_count:
        weights.extend([1] * (segment_count - len(weights)))
    total_weight = sum(weights) or segment_count
    raw = [usable_total * (weight / total_weight) for weight in weights]
    durations = [max(0.8, value) for value in raw]
    diff = usable_total - sum(durations)
    durations[-1] = max(0.8, durations[-1] + diff)
    return [round(value, 3) for value in durations]


def _build_segment_clip(source: Path, duration_sec: float, output_path: Path, fps: str, res: str) -> None:
    width = int(res)
    height = int(round(width * 16 / 9))
    if source.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"}:
        cmd = [
            "ffmpeg",
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(source),
            "-t",
            f"{duration_sec:.3f}",
            "-vf",
            f"scale={width}:{height},fps={fps},format=yuv420p",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(source),
            "-t",
            f"{duration_sec:.3f}",
            "-vf",
            (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=white,"
                f"fps={fps},format=yuv420p"
            ),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
    run_checked(cmd)


def _ffmpeg_escape_filter_path(path: Path) -> str:
    raw = str(path).replace("\\", "\\\\")
    for char in (":", "'", "[", "]", ",", ";"):
        raw = raw.replace(char, f"\\{char}")
    return raw


def _ffmpeg_escape_concat_path(path: Path) -> str:
    return str(path).replace("'", "'\\''")


def _sync_draft_to_mirror_root(draft_dir: Path, mirror_root: Path | None) -> Path | None:
    if mirror_root is None:
        return None
    source = draft_dir.expanduser()
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(f"Draft directory missing for mirror sync: {source}")

    target_root = mirror_root.expanduser()
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / source.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)

    for name in ("root_meta_info.json", "root_meta_info.json.bak"):
        meta_source = source.parent / name
        if meta_source.exists() and meta_source.is_file():
            shutil.copy2(meta_source, target_root / name)
    return target


def _manual_export_with_ffmpeg(
    *,
    parsed: dict,
    stage_script: Path,
    images_used: list[Path],
    output_video: Path,
    fps: str,
    res: str,
) -> dict:
    audio_path = Path(str(parsed.get("audio_path") or "")).expanduser().resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio missing for manual export: {audio_path}")

    srt_path = Path(str(parsed.get("srt_path") or "")).expanduser().resolve()
    total_duration = float(parsed.get("audio_duration_sec") or 0.0)
    if total_duration <= 0:
        raise RuntimeError("audio_duration_sec missing from pipeline report")

    stage_sections = _parse_plain_script_sections(stage_script)
    sources = _extract_still_clip_paths(parsed, len(images_used)) or list(images_used)
    if not sources:
        raise RuntimeError("No stage sources available for manual ffmpeg export")

    durations = _allocate_segment_durations(stage_sections, total_duration, len(sources))
    bgm_path_raw = str((parsed.get("bgm_report") or {}).get("track_path") or "").strip()
    bgm_path = Path(bgm_path_raw).expanduser().resolve() if bgm_path_raw else None
    if bgm_path and not bgm_path.exists():
        bgm_path = None

    output_video.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aki-video-export-") as tmpdir:
        tmp = Path(tmpdir)
        segment_paths: list[Path] = []
        for idx, (source, duration) in enumerate(zip(sources, durations), start=1):
            segment_path = tmp / f"segment_{idx:02d}.mp4"
            _build_segment_clip(source, duration, segment_path, fps=fps, res=res)
            segment_paths.append(segment_path)

        concat_file = tmp / "segments.txt"
        concat_file.write_text(
            "\n".join(f"file '{_ffmpeg_escape_concat_path(path)}'" for path in segment_paths) + "\n",
            encoding="utf-8",
        )

        visual_path = tmp / "visual.mp4"
        run_checked(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                str(visual_path),
            ]
        )

        av_path = tmp / "av.mp4"
        if bgm_path:
            run_checked(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(visual_path),
                    "-i",
                    str(audio_path),
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(bgm_path),
                    "-filter_complex",
                    (
                        f"[2:a]atrim=0:{total_duration:.3f},asetpts=N/SR/TB,volume=0.12[bgm];"
                        "[1:a][bgm]amix=inputs=2:weights=1 0.3:normalize=0[aout]"
                    ),
                    "-map",
                    "0:v",
                    "-map",
                    "[aout]",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(av_path),
                ]
            )
        else:
            run_checked(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(visual_path),
                    "-i",
                    str(audio_path),
                    "-map",
                    "0:v",
                    "-map",
                    "1:a",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(av_path),
                ]
            )

        if srt_path.exists():
            run_checked(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(av_path),
                    "-vf",
                    f"subtitles='{_ffmpeg_escape_filter_path(srt_path)}'",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "20",
                    "-c:a",
                    "copy",
                    str(output_video),
                ]
            )
        else:
            shutil.copy2(av_path, output_video)

    return {
        "command": ["ffmpeg_manual_export"],
        "exit_code": 0,
        "stdout": "manual ffmpeg export completed",
        "stderr": "",
        "ok": True,
    }


def _build_stage_assets(layout, platform: str) -> tuple[list[Path], Path, str]:
    timeline = load_json_file(layout.video_timeline_path(platform))
    segments = timeline.get("segments") or []
    if not segments:
        raise RuntimeError(f"No timeline segments found for {platform}")

    stage_dir = layout.video_stage_dir(platform)
    stage_images = layout.video_stage_images_dir(platform)
    stage_script = layout.video_stage_script_path(platform)
    stage_dir.mkdir(parents=True, exist_ok=True)
    script_override = _load_script_override(layout, platform, len(segments))
    preserved_stage_script, preserved_stage_source = _select_stage_script_text(stage_script, script_override)
    clear_directory(stage_dir)
    stage_images.mkdir(parents=True, exist_ok=True)

    image_paths: list[Path] = []
    for segment in segments:
        image_path = Path(str(segment.get("image_path") or "")).expanduser().resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"Timeline image missing: {image_path}")
        image_paths.append(image_path)

    copied = copy_selected_images(image_paths, stage_images)
    if preserved_stage_script:
        stage_script.write_text(preserved_stage_script + "\n", encoding="utf-8")
        return copied, stage_script, str(preserved_stage_source or stage_script)

    override_lines = script_override[0] if script_override else None
    script_source = script_override[1] if script_override else str(layout.video_timeline_path(platform))

    spoken_lines: list[str] = []
    for idx, segment in enumerate(segments):
        script_text = (
            str(override_lines[idx]).strip()
            if override_lines is not None
            else str(segment.get("tts_script") or segment.get("script") or "").strip()
        )
        if not script_text:
            raise RuntimeError(f"Timeline segment missing script text: {segment.get('slot')}")
        spoken_lines.append(script_text)

    stage_script.write_text("\n\n".join(spoken_lines).strip() + "\n", encoding="utf-8")
    return copied, stage_script, script_source


def _build_one_platform(layout, platform: str, args: argparse.Namespace) -> tuple[bool, dict]:
    if not layout.video_timeline_path(platform).exists():
        raise FileNotFoundError(f"Timeline missing: {layout.video_timeline_path(platform)}")
    if not layout.video_voice_script_path(platform).exists():
        raise FileNotFoundError(f"Voice script missing: {layout.video_voice_script_path(platform)}")
    if not VIDEO_PIPELINE.exists():
        raise FileNotFoundError(f"Video pipeline script missing: {VIDEO_PIPELINE}")
    export_strategy = _choose_export_strategy(force_export=bool(args.force_export))
    if export_strategy == "native_auto_export" and not AUTO_EXPORTER.exists():
        raise FileNotFoundError(f"Auto exporter missing: {AUTO_EXPORTER}")

    copied, stage_script, script_source = _build_stage_assets(layout, platform)
    output_dir = layout.video_output_dir(platform)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_video = layout.video_output_video_path(platform)
    json_report = output_dir / "nl_report.json"

    suffix = VIDEO_PLATFORM_CONFIG[platform]["draft_suffix"]
    draft_name = _safe_draft_name(layout.root.name, suffix=suffix)
    pipeline_cmd = [
        "python3",
        str(VIDEO_PIPELINE),
        "--project-dir",
        str(layout.video_stage_dir(platform)),
        "--intent",
        "generate_draft",
        "--voice-name",
        args.voice_name,
        "--speed-override",
        str(args.speed_override),
        "--bgm-mode",
        str(args.bgm_mode),
        "--bgm-min-duration-sec",
        str(args.bgm_min_duration_sec),
        "--subtitle-font",
        str(args.subtitle_font),
        "--subtitle-font-size",
        str(args.subtitle_font_size),
        "--subtitle-style",
        str(args.subtitle_style),
        "--subtitle-max-chars",
        str(args.subtitle_max_chars),
        "--subtitle-max-duration",
        str(args.subtitle_max_duration),
        "--image-fit-mode",
        str(args.image_fit_mode),
        "--content-bbox-threshold",
        str(args.content_bbox_threshold),
        "--bg-extension-blur",
        str(args.bg_extension_blur),
        "--animation-preset",
        str(args.animation_preset),
        "--new-name",
        draft_name,
        "--json-report",
        str(json_report),
    ]
    pipeline_run = _run_cmd(pipeline_cmd)
    if not pipeline_run["ok"]:
        report = {"platform": platform, "pipeline": pipeline_run, "images_used": [str(p) for p in copied]}
        report_path = layout.video_export_report_path(platform)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return False, {"report_path": str(report_path), "report": report}

    parsed = _extract_json_tail(pipeline_run["stdout"])
    draft = str(parsed.get("draft_name") or draft_name)
    export_skipped = export_strategy == "skip_unsupported"
    export_skip_reason = ""
    draft_dir = Path(
        str(parsed.get("draft_path") or (default_jianying_projects_root(repo_root_path=REPO_ROOT) / draft))
    ).expanduser()
    mirrored_draft_dir = None
    if export_strategy == "skip_unsupported":
        export_skipped = True
        export_skip_reason = f"auto exporter unsupported on platform: {sys.platform}"
        export_run = {"command": [], "exit_code": 0, "stdout": "", "stderr": "", "ok": True}
    elif export_strategy == "unsupported_force_export":
        export_run = {
            "command": [],
            "exit_code": 1,
            "stdout": "",
            "stderr": "ffmpeg/ffprobe unavailable on current platform for manual export",
            "ok": False,
        }
    elif export_strategy == "ffmpeg_fallback":
        export_run = _manual_export_with_ffmpeg(
            parsed=parsed,
            stage_script=stage_script,
            images_used=copied,
            output_video=output_video,
            fps=args.fps,
            res=args.res,
        )
    else:
        export_cmd = [
            "python3",
            str(AUTO_EXPORTER),
            draft,
            str(output_video),
            "--res",
            args.res,
            "--fps",
            args.fps,
        ]
        export_run = _run_cmd(export_cmd)

    mirror_root = default_jianying_sync_root()
    if mirror_root and draft_dir.exists():
        mirrored_draft_dir = _sync_draft_to_mirror_root(draft_dir, mirror_root)

    report = {
        "platform": platform,
        "pipeline": pipeline_run,
        "parsed_pipeline_json": parsed,
        "export": export_run,
        "export_strategy": export_strategy,
        "export_skipped": export_skipped,
        "export_skip_reason": export_skip_reason,
        "draft_only": bool(export_skipped and not Path(output_video).exists()),
        "output_video": str(output_video),
        "draft_dir": str(draft_dir),
        "draft_mirror_dir": str(mirrored_draft_dir) if mirrored_draft_dir else None,
        "images_used": [str(p) for p in copied],
        "stage_script": str(stage_script),
        "script_source": script_source,
    }
    report_path = layout.video_export_report_path(platform)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return (pipeline_run["ok"] and export_run["ok"]), {"report_path": str(report_path), "report": report}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build per-platform JianYing drafts from timeline+images")
    parser.add_argument("--topic-root", required=True)
    parser.add_argument("--platforms", default="auto", help="auto|all|wechat,xiaohongshu,douyin")
    parser.add_argument("--mode", choices=["prod", "test"], default="prod")
    parser.add_argument("--voice-name", default="日常松弛男")
    parser.add_argument("--speed-override", type=float, default=1.08)
    parser.add_argument("--bgm-mode", default="favorites_first_controlled_fallback")
    parser.add_argument("--bgm-min-duration-sec", type=float, default=45.0)
    parser.add_argument("--subtitle-font", default="莫雪体")
    parser.add_argument("--subtitle-font-size", type=float, default=10.0)
    parser.add_argument("--subtitle-style", default="yellow_preset")
    parser.add_argument("--subtitle-max-chars", type=int, default=34)
    parser.add_argument("--subtitle-max-duration", type=float, default=4.6)
    parser.add_argument(
        "--image-fit-mode",
        default="contain_with_bg_extension",
        choices=["contain_preserve", "contain_center_by_content", "contain_with_bg_extension"],
    )
    parser.add_argument("--content-bbox-threshold", type=int, default=245)
    parser.add_argument("--bg-extension-blur", type=float, default=0.75)
    parser.add_argument(
        "--animation-preset",
        default="zoom_group_ii",
        choices=["none", "flip_zoom", "zoom_combo", "zoom_group_ii"],
    )
    parser.add_argument("--res", default="1080")
    parser.add_argument("--fps", default="30")
    parser.add_argument(
        "--force-export",
        action="store_true",
        help="Force running auto exporter even on unsupported platforms",
    )
    args = parser.parse_args()

    layout = resolve_layout(args.topic_root)
    platforms = _parse_platforms(args.platforms, args.mode)
    set_step(layout.root, "build_video_package", RUNNING, message=f"Building video package for {', '.join(platforms)}")

    overall_ok = True
    platform_reports: dict[str, str] = {}
    draft_only_platforms: list[str] = []
    try:
        for platform in platforms:
            ok, payload = _build_one_platform(layout, platform, args)
            platform_reports[platform] = str(payload["report_path"])
            set_artifact(layout.root, f"video_export_report_{platform}", str(payload["report_path"]))
            output_video = Path(str(payload["report"].get("output_video") or "")).expanduser()
            if output_video.exists():
                set_artifact(layout.root, f"video_output_{platform}", str(output_video))
                if payload["report"].get("export_strategy") == "ffmpeg_fallback":
                    set_artifact(layout.root, "manual_mp4_export", str(output_video))
            if payload["report"].get("draft_only"):
                draft_only_platforms.append(platform)
            overall_ok = overall_ok and ok
    except Exception as exc:
        set_step(layout.root, "build_video_package", FAILED, message=str(exc))
        raise

    if not overall_ok:
        set_step(
            layout.root,
            "build_video_package",
            FAILED,
            message="At least one platform video build failed",
            meta={"reports": platform_reports},
        )
        if platform_reports:
            print(json.dumps(platform_reports, ensure_ascii=False, indent=2))
        return 1

    done_message = "Video package generated"
    if draft_only_platforms:
        done_message = "JianYing draft generated; mp4 export skipped on current platform"
    set_step(
        layout.root,
        "build_video_package",
        DONE,
        message=done_message,
        meta={"reports": platform_reports, "platforms": platforms, "draft_only_platforms": draft_only_platforms},
    )
    print(json.dumps(platform_reports, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
