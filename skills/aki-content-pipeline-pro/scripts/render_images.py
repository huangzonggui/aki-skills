#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content_plan import load_plan
from state import DONE, FAILED, RUNNING, set_artifact, set_step
from topic_layout import DEFAULT_RENDER_PLATFORMS_BY_MODE, IMAGE_PLATFORMS, resolve_layout
from utils import (
    clear_directory,
    clear_image_files,
    convert_image_to_jpg,
    ensure_dir,
    list_image_files,
)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(os.getenv("AKI_SKILLS_REPO_ROOT", "")).expanduser().resolve() if os.getenv("AKI_SKILLS_REPO_ROOT") else SCRIPT_DIR.parents[2]
SHARED_DIR = REPO_ROOT / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from aki_runtime import skill_path  # noqa: E402


SERIES_SCRIPT_DIR = skill_path("aki-dense-handnote-series", "scripts", repo_root_path=REPO_ROOT)
if str(SERIES_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SERIES_SCRIPT_DIR))

from generate_handnote_series import generate_image_with_comfly, load_image_api_settings  # type: ignore


DEFAULT_UNIT_COST_CNY = 0.6


def _extract_prompt_title(path: Path) -> str:
    if not path.exists():
        return "(missing)"
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("#"):
            return text.lstrip("#").strip() or "(empty heading)"
        return text[:120]
    return "(empty)"


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
    if not items:
        raise ValueError("No platforms selected")
    return items


def _write_prompt_files(topic_root: Path) -> tuple[list[Path], Path]:
    layout = resolve_layout(topic_root)
    plan = load_plan(layout.content_plan_path)
    ensure_dir(layout.prompts_dir)
    for old in layout.prompts_dir.glob("series_*_prompt.md"):
        old.unlink()

    prompt_files: list[Path] = []
    cover_prompt = str(plan.get("cover_prompt") or "").strip()
    if cover_prompt:
        cover_path = layout.prompts_dir / "cover_prompt.md"
        cover_path.write_text(cover_prompt if cover_prompt.endswith("\n") else cover_prompt + "\n", encoding="utf-8")
        prompt_files.append(cover_path)
    else:
        cover_path = layout.prompts_dir / "cover_prompt.md"
        if cover_path.exists():
            cover_path.unlink()

    series_prompts = plan.get("series_prompts") or []
    width = max(2, len(str(len(series_prompts))))
    for idx, prompt in enumerate(series_prompts, start=1):
        path = layout.prompts_dir / f"series_{idx:0{width}d}_prompt.md"
        text = str(prompt).rstrip() + "\n"
        path.write_text(text, encoding="utf-8")
        prompt_files.append(path)

    review_lines = ["# Prompt Title Review", ""]
    for file in prompt_files:
        review_lines.append(f"- `{file.relative_to(layout.root)}` -> {_extract_prompt_title(file)}")
    layout.prompt_review_path.write_text("\n".join(review_lines).strip() + "\n", encoding="utf-8")
    return prompt_files, layout.prompt_review_path


def _collect_prompt_files(layout) -> tuple[Path | None, list[Path]]:
    cover = layout.prompts_dir / "cover_prompt.md"
    series = sorted(layout.prompts_dir.glob("series_*_prompt.md"))
    return (cover if cover.exists() else None), series


def _render_prompt_to_file(prompt_path: Path, output_path: Path, settings: dict[str, Any]) -> None:
    prompt_text = prompt_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not prompt_text:
        raise RuntimeError(f"Prompt file is empty: {prompt_path}")
    generate_image_with_comfly(prompt_text, output_path, settings)


def _write_publish_jpg(original_png_path: Path, publish_jpg_path: Path) -> Path:
    convert_image_to_jpg(original_png_path, publish_jpg_path)
    return publish_jpg_path


def _render_platform_images(layout, platform: str, settings: dict[str, Any]) -> dict[str, int]:
    image_dir = layout.platform_images_dir(platform)
    originals_dir = layout.platform_original_images_dir(platform)
    image_dir.mkdir(parents=True, exist_ok=True)
    originals_dir.mkdir(parents=True, exist_ok=True)
    clear_image_files(image_dir)

    cover_prompt, series_prompts = _collect_prompt_files(layout)
    if cover_prompt is None and not series_prompts:
        raise RuntimeError(f"No prompt files found under {layout.prompts_dir}")
    original_png_count = 0
    jpg_count = 0
    if cover_prompt:
        cover_png = originals_dir / "cover_01.png"
        cover_jpg = image_dir / "cover_01.jpg"
        _render_prompt_to_file(cover_prompt, cover_png, settings)
        original_png_count += 1
        _write_publish_jpg(cover_png, cover_jpg)
        jpg_count += 1

    for idx, prompt_path in enumerate(series_prompts, start=1):
        out_png = originals_dir / f"series_{idx:02d}.png"
        out_jpg = image_dir / f"series_{idx:02d}.jpg"
        _render_prompt_to_file(prompt_path, out_png, settings)
        original_png_count += 1
        _write_publish_jpg(out_png, out_jpg)
        jpg_count += 1

    return {"png": original_png_count, "original_png": original_png_count, "jpg": jpg_count}


def _write_cost_summary(layout, mode: str, unit_cost_cny: float, platforms: list[str]) -> tuple[Path, Path, dict[str, Any]]:
    counts: dict[str, dict[str, int]] = {}
    total_billed_images = 0
    total_jpg_derivatives = 0
    for platform in platforms:
        publish_files = list_image_files(layout.platform_images_dir(platform))
        original_files = list_image_files(layout.platform_original_images_dir(platform))
        png_count = len([path for path in original_files if path.suffix.lower() == ".png"])
        jpg_count = len([path for path in publish_files if path.suffix.lower() in {".jpg", ".jpeg"}])
        counts[platform] = {
            "png": png_count,
            "original_png": png_count,
            "jpg": jpg_count,
            "billed_images": png_count,
            "publish_ready_images": jpg_count,
        }
        total_billed_images += png_count
        total_jpg_derivatives += jpg_count

    estimated_total_cost_cny = round(total_billed_images * unit_cost_cny, 2)
    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "platforms": platforms,
        "unit_cost_cny": round(unit_cost_cny, 2),
        "counts": counts,
        "total_billed_images": total_billed_images,
        "total_jpg_derivatives": total_jpg_derivatives,
        "estimated_total_cost_cny": estimated_total_cost_cny,
        "formula": f"{round(unit_cost_cny, 2)} * {total_billed_images}",
    }

    md_lines = [
        "# Image Cost Summary",
        "",
        f"- Generated at (UTC): {summary['generated_at']}",
        f"- Mode: {mode}",
        f"- Platforms: {', '.join(platforms)}",
        f"- Unit cost: {round(unit_cost_cny, 2):.2f} CNY / rendered image",
        "",
        "## Platform Counts",
        "",
    ]
    for platform in platforms:
        row = counts[platform]
        md_lines.append(
            f"- {platform}: original_png={row['original_png']}, jpg={row['jpg']}, "
            f"publish_ready={row['publish_ready_images']}, billed={row['billed_images']}"
        )
    md_lines.extend(
        [
            "",
            f"- Total billed images: {total_billed_images}",
            f"- JPG derivatives: {total_jpg_derivatives}",
            f"- Estimated total cost: {estimated_total_cost_cny:.2f} CNY ({summary['formula']})",
        ]
    )
    layout.image_cost_summary_md.write_text("\n".join(md_lines).strip() + "\n", encoding="utf-8")
    layout.image_cost_summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return layout.image_cost_summary_md, layout.image_cost_summary_json, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Write unified prompt files and render per-platform image sets")
    parser.add_argument("--topic-root", required=True)
    parser.add_argument("--mode", choices=["prod", "test"], default="prod")
    parser.add_argument("--stage", choices=["prompts", "render", "all"], default="all")
    parser.add_argument("--approved-titles", action="store_true")
    parser.add_argument("--platforms", default="auto", help="auto|all|wechat,xiaohongshu,douyin")
    parser.add_argument(
        "--unit-cost",
        type=float,
        default=DEFAULT_UNIT_COST_CNY,
        help="Estimated unit cost in CNY per rendered prompt image (default: 0.6)",
    )
    args = parser.parse_args()

    if args.unit_cost < 0:
        raise ValueError("--unit-cost must be >= 0")

    layout = resolve_layout(args.topic_root)
    if not layout.content_plan_path.exists():
        raise FileNotFoundError(f"Content plan not found: {layout.content_plan_path}")

    prompt_files: list[Path] = []
    review_path: Path | None = None
    if args.stage in {"prompts", "all"}:
        set_step(layout.root, "generate_prompts", RUNNING, message="Writing unified prompt files")
        try:
            prompt_files, review_path = _write_prompt_files(layout.root)
        except Exception as exc:
            set_step(layout.root, "generate_prompts", FAILED, message=str(exc))
            raise
        set_artifact(layout.root, "prompt_review", str(review_path))
        set_step(
            layout.root,
            "generate_prompts",
            DONE,
            message="Unified prompt files generated",
            meta={"review": str(review_path), "prompt_count": len(prompt_files)},
        )
        if args.stage == "prompts":
            print(str(review_path))
            return 0
        if not args.approved_titles:
            print(str(review_path))
            return 2

    if args.stage == "render" and not args.approved_titles:
        raise ValueError("render stage requires --approved-titles")

    platforms = _parse_platforms(args.platforms, args.mode)
    settings = load_image_api_settings(SERIES_SCRIPT_DIR.parent)
    set_step(layout.root, "render_images", RUNNING, message=f"Rendering images for {', '.join(platforms)}")
    try:
        results: dict[str, dict[str, int]] = {}
        for platform in platforms:
            results[platform] = _render_platform_images(layout, platform, settings)
        cost_md, cost_json, summary = _write_cost_summary(layout, args.mode, args.unit_cost, platforms)
        set_artifact(layout.root, "image_cost_summary_md", str(cost_md))
        set_artifact(layout.root, "image_cost_summary_json", str(cost_json))
        set_artifact(layout.root, "rendered_platforms", platforms)
        set_artifact(layout.root, "render_image_counts", results)
    except Exception as exc:
        set_step(layout.root, "render_images", FAILED, message=str(exc))
        raise

    set_step(
        layout.root,
        "render_images",
        DONE,
        message=(
            "Image generation completed: "
            f"{summary['total_billed_images']} rendered image(s), "
            f"estimated cost ¥{float(summary['estimated_total_cost_cny']):.2f}"
        ),
        meta={
            "platforms": platforms,
            "total_billed_images": int(summary["total_billed_images"]),
            "estimated_cost_cny": float(summary["estimated_total_cost_cny"]),
            "cost_summary_md": str(cost_md),
            "cost_summary_json": str(cost_json),
        },
    )
    print(str(cost_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
