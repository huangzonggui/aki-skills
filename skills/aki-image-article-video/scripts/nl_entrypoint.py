#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from bgm_selector import choose_bgm, update_feedback
from pipeline_config import load_pipeline_config
from voice_registry import get_profile, update_voice_uri, upsert_profile


SCRIPT_DIR = Path(__file__).resolve().parent
BUILD_SCRIPT = SCRIPT_DIR / "build_video_from_article_assets.py"
DRAFT_ENHANCER = SCRIPT_DIR / "draft_enhancer.py"
STILL_IMAGE_REPAIR = SCRIPT_DIR / "repair_still_image_draft.py"


def _run(cmd: list[str]) -> str:
    cp = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return (cp.stdout or "").strip()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_name(raw: str) -> str:
    s = re.sub(r"[^\w\-一-龥]+", "_", raw.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:64] or "draft"


def find_existing_script(project_dir: Path) -> Path | None:
    candidates: list[tuple[int, float, Path]] = []
    patterns = (".md", ".txt")
    for p in project_dir.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in patterns:
            continue
        n = p.name.lower()
        score = -1
        if "口播稿" in p.name:
            score = 100
        elif "口播脚本" in p.name:
            score = 95
        elif "script" in n:
            score = 90
        elif "脚本" in p.name:
            score = 80
        if score >= 0:
            candidates.append((score, p.stat().st_mtime, p))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def collect_markdowns(project_dir: Path) -> list[Path]:
    out: list[Path] = []
    for p in project_dir.rglob("*.md"):
        if not p.is_file():
            continue
        if ".local" in p.parts:
            continue
        parts_lower = {part.lower() for part in p.parts}
        name_lower = p.name.lower()
        if "prompts" in parts_lower:
            continue
        if name_lower in {"outline.md"}:
            continue
        if "handnote-cover" in name_lower:
            continue
        out.append(p)
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)


def build_merged_article(md_files: list[Path], output: Path) -> Path:
    chunks: list[str] = []
    for p in md_files:
        txt = p.read_text(encoding="utf-8", errors="ignore").strip()
        if not txt:
            continue
        chunks.append(f"# {p.stem}\n\n{txt}\n")
    if not chunks:
        raise RuntimeError("no markdown content available for summary")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n\n".join(chunks), encoding="utf-8")
    return output


def collect_images(project_dir: Path) -> list[Path]:
    exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    images = [p.resolve() for p in project_dir.rglob("*") if p.is_file() and p.suffix.lower() in exts]
    images.sort(key=lambda p: p.name.lower())
    return images


def main() -> None:
    cfg = load_pipeline_config()
    parser = argparse.ArgumentParser(description="Natural-language entrypoint for aki-image-article-video")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument(
        "--intent",
        default="generate_draft",
        choices=["generate_draft", "register_voice_profile", "bgm_feedback"],
    )
    parser.add_argument("--voice-name", default="日常松弛男")
    parser.add_argument("--speed-override", type=float, default=None)
    parser.add_argument(
        "--voice-fallback-policy",
        default="strict",
        choices=["strict", "edge"],
        help="strict: keep requested voice only; edge: fallback to edge-tts on provider failure",
    )
    parser.add_argument(
        "--script-format",
        default="auto",
        choices=["auto", "verbatim"],
    )
    parser.add_argument("--subtitle-mode", default="asr", choices=["asr", "heuristic"])
    parser.add_argument(
        "--subtitle-engine",
        default="stable_regroup",
        choices=["stable_regroup", "legacy"],
    )
    parser.add_argument(
        "--subtitle-qa-policy",
        default="strict",
        choices=["strict", "medium", "off"],
    )
    parser.add_argument("--subtitle-font", default="本黑体")
    parser.add_argument("--subtitle-max-chars", type=int, default=26)
    parser.add_argument("--subtitle-max-duration", type=float, default=3.2)
    parser.add_argument("--script-editor-cmd", default="")
    parser.add_argument("--script-editor-timeout-sec", type=int, default=180)
    parser.add_argument("--bgm-mode", default="auto_tech_from_jy_cache")
    parser.add_argument("--bgm-min-duration-sec", type=float, default=45.0)
    parser.add_argument("--new-name", default="")
    parser.add_argument("--json-report", default="")

    # registration inputs
    parser.add_argument("--voice-provider", default="siliconflow")
    parser.add_argument("--voice-model", default="IndexTeam/IndexTTS-2")
    parser.add_argument("--voice-default-speed", type=float, default=None)
    parser.add_argument("--voice-ref-audio", default="")
    parser.add_argument("--voice-uri", default="")
    parser.add_argument("--voice-notes", default="")

    # feedback inputs
    parser.add_argument("--bgm-track-path", default="")
    parser.add_argument("--bgm-feedback", default="")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).expanduser().resolve()
    if not project_dir.exists():
        raise FileNotFoundError(f"project_dir not found: {project_dir}")

    profile_file = cfg.voice_profile_path
    history_file = cfg.voice_profile_path.parent / "bgm_history.json"
    warnings: list[str] = []

    if args.intent == "register_voice_profile":
        p = upsert_profile(
            profile_path=profile_file,
            voice_name=args.voice_name,
            provider=args.voice_provider,
            model=args.voice_model,
            default_speed=args.voice_default_speed,
            ref_audio_path=args.voice_ref_audio,
            voice_uri=args.voice_uri,
            notes=args.voice_notes,
        )
        out = {"ok": True, "intent": args.intent, "profile": p.__dict__, "profile_file": str(profile_file)}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if args.intent == "bgm_feedback":
        if not args.bgm_track_path or not args.bgm_feedback:
            raise ValueError("bgm_feedback intent needs --bgm-track-path and --bgm-feedback")
        report = update_feedback(
            history_file=history_file,
            track_path=Path(args.bgm_track_path).expanduser().resolve(),
            feedback=args.bgm_feedback,
        )
        print(json.dumps({"ok": True, "intent": args.intent, "report": report}, ensure_ascii=False, indent=2))
        return

    # generate_draft
    voice_profile = get_profile(profile_file, args.voice_name)
    if args.speed_override is not None:
        speed = args.speed_override
    elif float(getattr(voice_profile, "default_speed", 0.0) or 0.0) > 0:
        speed = float(voice_profile.default_speed)
    elif args.voice_name == "日常松弛男":
        speed = 1.2
    else:
        speed = 1.0

    script_file = find_existing_script(project_dir)
    merged_article_path: Path | None = None
    if script_file is None:
        md_files = collect_markdowns(project_dir)
        if not md_files:
            raise RuntimeError("no script candidate and no markdown files for summary")
        merged_article_path = build_merged_article(
            md_files,
            cfg.runtime_reports_dir / f"{_safe_name(project_dir.name)}__merged_article.md",
        )

    images = collect_images(project_dir)
    if not images:
        raise RuntimeError(f"no image assets in {project_dir}")
    assets_csv = ",".join(str(p) for p in images)

    stamp = time.strftime("%m%d_%H%M%S")
    draft_name = args.new_name.strip() or f"{_safe_name(project_dir.name)}_auto_{stamp}"
    build_report_path = cfg.runtime_reports_dir / f"{draft_name}__build.json"
    enh_report_path = cfg.runtime_reports_dir / f"{draft_name}__enhancer.json"
    final_report_path = (
        Path(args.json_report).expanduser().resolve()
        if args.json_report
        else cfg.runtime_reports_dir / f"{draft_name}__final.json"
    )

    tts_provider = voice_profile.provider or "siliconflow"
    cmd = [
        "python3",
        str(BUILD_SCRIPT),
        "--new-name",
        draft_name,
        "--projects-root",
        str(cfg.jy_projects_root),
        "--workdir",
        str(cfg.runtime_reports_dir),
        "--assets",
        assets_csv,
        "--subtitle-mode",
        args.subtitle_mode,
        "--subtitle-engine",
        args.subtitle_engine,
        "--subtitle-qa-policy",
        args.subtitle_qa_policy,
        "--subtitle-font",
        args.subtitle_font,
        "--subtitle-max-chars",
        str(args.subtitle_max_chars),
        "--subtitle-max-duration",
        str(args.subtitle_max_duration),
        "--subtitle-text-source",
        "script",
        "--tts-provider",
        tts_provider,
        "--voice-speed",
        f"{speed}",
        "--script-format",
        args.script_format,
        "--script-editor-timeout-sec",
        str(args.script_editor_timeout_sec),
        "--keys-env-file",
        str(cfg.ai_keys_env_path),
        "--smart-cut-mode",
        "structured",
        "--json-report",
        str(build_report_path),
        "--transition-primary",
        "翻页",
        "--transition-fallback",
        "叠化",
    ]

    if script_file is not None:
        cmd.extend(["--script-file", str(script_file)])
    else:
        cmd.extend(["--article", str(merged_article_path)])
    if args.script_editor_cmd.strip():
        cmd.extend(["--script-editor-cmd", args.script_editor_cmd.strip()])

    if tts_provider == "siliconflow":
        allow_edge_fallback = args.voice_fallback_policy == "edge"
        if allow_edge_fallback:
            cmd.append("--fallback-edge-on-siliconflow-fail")
        cmd.append("--force-atempo-speed")
        if voice_profile.model:
            cmd.extend(["--siliconflow-model", voice_profile.model])
        if voice_profile.voice_uri:
            cmd.extend(["--siliconflow-voice-uri", voice_profile.voice_uri])
        elif voice_profile.ref_audio_path:
            ref_audio = Path(voice_profile.ref_audio_path).expanduser().resolve()
            if ref_audio.exists():
                cmd.extend(["--siliconflow-ref-audio", str(ref_audio)])
            else:
                msg = f"voice ref audio missing: {ref_audio}"
                if allow_edge_fallback:
                    warnings.append(msg)
                else:
                    raise RuntimeError(msg)
        else:
            msg = f"voice profile '{args.voice_name}' missing voice_uri/ref_audio_path"
            if allow_edge_fallback:
                warnings.append(msg)
            else:
                raise RuntimeError(msg)
    elif tts_provider == "minimax":
        cmd.extend(["--minimax-voice-name", args.voice_name])
        if args.voice_fallback_policy == "edge":
            cmd.append("--fallback-edge-on-minimax-fail")

    _run(cmd)
    build_report = _read_json(build_report_path)
    repair_report: dict[str, Any] = {}
    if STILL_IMAGE_REPAIR.exists() and build_report.get("draft_path"):
        repair_cmd = [
            "python3",
            str(STILL_IMAGE_REPAIR),
            "--draft-dir",
            str(build_report["draft_path"]),
            "--json-report",
            str(cfg.runtime_reports_dir / f"{draft_name}__still_image_repair.json"),
        ]
        _run(repair_cmd)
        repair_report = _read_json(cfg.runtime_reports_dir / f"{draft_name}__still_image_repair.json")

    bgm_pick = choose_bgm(
        music_dir=cfg.jy_cache_music_dir,
        history_file=history_file,
        mode=args.bgm_mode,
        min_music_duration_sec=float(args.bgm_min_duration_sec),
        projects_root=cfg.jy_projects_root,
        prefer_jy_favorite_commercial=True,
    )
    enh_cmd = [
        "python3",
        str(DRAFT_ENHANCER),
        "--draft-dir",
        str(build_report["draft_path"]),
        "--animation-preset",
        "flip_zoom",
        "--disable-bgm-speech-follow",
        "--json-report",
        str(enh_report_path),
    ]
    if bgm_pick.get("ok") and bgm_pick.get("track_path"):
        enh_cmd.extend(["--bgm-path", str(bgm_pick["track_path"])])
    else:
        warnings.append(f"BGM unavailable: {bgm_pick.get('reason', 'unknown')}")
    _run(enh_cmd)
    enh_report = _read_json(enh_report_path)

    voice_uri_used = str(build_report.get("voice_uri_used", "") or "")
    if tts_provider == "siliconflow" and voice_uri_used:
        update_voice_uri(profile_file, args.voice_name, voice_uri_used)

    warnings.extend(build_report.get("warnings", []))
    warnings.extend(enh_report.get("warnings", []))

    final = {
        "draft_name": build_report.get("draft_name", draft_name),
        "draft_path": build_report.get("draft_path"),
        "script_path": build_report.get("script_path"),
        "audio_path": build_report.get("audio_path"),
        "srt_path": build_report.get("srt_path"),
        "voice_uri_used": voice_uri_used,
        "audio_duration_sec": build_report.get("audio_duration_sec"),
        "cpm_report": build_report.get("cpm_report", {}),
        "speed_report": build_report.get("speed_report", {}),
        "subtitle_report": build_report.get("subtitle_report", {}),
        "draft_asset_repair": repair_report,
        "bgm_report": {
            "track_path": bgm_pick.get("track_path", ""),
            "source": bgm_pick.get("source", ""),
            "policy": bgm_pick.get("policy", args.bgm_mode),
            "jy_favorites": bgm_pick.get("jy_favorites", {}),
            "enhancer": enh_report.get("bgm", {}),
        },
        "warnings": [w for w in warnings if w],
    }
    final_report_path.parent.mkdir(parents=True, exist_ok=True)
    final_report_path.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(final, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
