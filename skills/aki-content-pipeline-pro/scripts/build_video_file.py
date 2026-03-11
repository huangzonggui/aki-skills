#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from state import DONE, FAILED, RUNNING, set_artifact, set_step
from topic_layout import DEFAULT_RENDER_PLATFORMS_BY_MODE, IMAGE_PLATFORMS, VIDEO_PLATFORM_CONFIG, resolve_layout
from utils import clear_directory, copy_selected_images, load_json_file, run


VIDEO_PIPELINE = Path(
    "/Users/aki/Development/code/aki-skills/skills/aki-image-article-video/scripts/nl_entrypoint.py"
)
AUTO_EXPORTER = Path("/Users/aki/.agents/skills/jianying-editor/scripts/auto_exporter.py")


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


def _build_stage_assets(layout, platform: str) -> tuple[list[Path], Path]:
    timeline = load_json_file(layout.video_timeline_path(platform))
    segments = timeline.get("segments") or []
    if not segments:
        raise RuntimeError(f"No timeline segments found for {platform}")

    stage_dir = layout.video_stage_dir(platform)
    stage_images = layout.video_stage_images_dir(platform)
    stage_script = layout.video_stage_script_path(platform)
    stage_dir.mkdir(parents=True, exist_ok=True)
    clear_directory(stage_dir)
    stage_images.mkdir(parents=True, exist_ok=True)

    image_paths: list[Path] = []
    spoken_lines: list[str] = []
    for segment in segments:
        image_path = Path(str(segment.get("image_path") or "")).expanduser().resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"Timeline image missing: {image_path}")
        script_text = str(segment.get("script") or "").strip()
        if not script_text:
            raise RuntimeError(f"Timeline segment missing script text: {segment.get('slot')}")
        image_paths.append(image_path)
        spoken_lines.append(script_text)

    copied = copy_selected_images(image_paths, stage_images)
    stage_script.write_text("\n\n".join(spoken_lines).strip() + "\n", encoding="utf-8")
    return copied, stage_script


def _build_one_platform(layout, platform: str, args: argparse.Namespace) -> tuple[bool, dict]:
    if not layout.video_timeline_path(platform).exists():
        raise FileNotFoundError(f"Timeline missing: {layout.video_timeline_path(platform)}")
    if not layout.video_voice_script_path(platform).exists():
        raise FileNotFoundError(f"Voice script missing: {layout.video_voice_script_path(platform)}")
    if not VIDEO_PIPELINE.exists():
        raise FileNotFoundError(f"Video pipeline script missing: {VIDEO_PIPELINE}")
    if not AUTO_EXPORTER.exists():
        raise FileNotFoundError(f"Auto exporter missing: {AUTO_EXPORTER}")

    copied, stage_script = _build_stage_assets(layout, platform)
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
    export_supported = sys.platform.startswith("win")
    export_skipped = False
    export_skip_reason = ""
    if not export_supported and not args.force_export:
        export_skipped = True
        export_skip_reason = f"auto exporter unsupported on platform: {sys.platform}"
        export_run = {"command": [], "exit_code": 0, "stdout": "", "stderr": "", "ok": True}
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

    report = {
        "platform": platform,
        "pipeline": pipeline_run,
        "parsed_pipeline_json": parsed,
        "export": export_run,
        "export_skipped": export_skipped,
        "export_skip_reason": export_skip_reason,
        "draft_only": bool(export_skipped and not Path(output_video).exists()),
        "output_video": str(output_video),
        "images_used": [str(p) for p in copied],
        "stage_script": str(stage_script),
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
    parser.add_argument("--speed-override", type=float, default=1.2)
    parser.add_argument("--bgm-mode", default="auto_tech_from_jy_cache")
    parser.add_argument("--bgm-min-duration-sec", type=float, default=45.0)
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
