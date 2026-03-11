#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from topic_layout import TopicLayout


BUNDLE_SCRIPT_DIR = Path(
    "/Users/aki/Development/code/aki-skills/skills/aki-dense-handnote-series/scripts"
)
if str(BUNDLE_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(BUNDLE_SCRIPT_DIR))

from generate_handnote_bundle import _build_bundle  # type: ignore


DEFAULT_CONTENT_MIN_PAGES = 3
DEFAULT_CONTENT_MAX_PAGES = 6
DEFAULT_ENDING_POLICY = "adaptive"
DEFAULT_LOGIC_MODE = "hybrid"
DEFAULT_METADATA_LEVEL = "verbose"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _preview_text(text: str, limit: int = 120) -> str:
    single = " ".join(text.replace("\r", " ").replace("\n", " ").split()).strip()
    if len(single) <= limit:
        return single
    return single[: limit - 1].rstrip() + "…"


def _page_source_text(page: dict[str, Any]) -> str:
    parts: list[str] = []
    for unit in page.get("units") or []:
        heading = str(unit.get("heading") or "").strip()
        text = str(unit.get("text") or "").strip()
        if heading:
            parts.append(f"### {heading}\n{text}".strip())
        elif text:
            parts.append(text)
    return "\n\n".join(part for part in parts if part).strip()


def _serialize_pages(pages: list[Any]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for idx, page in enumerate(pages, start=1):
        units: list[dict[str, Any]] = []
        char_count = 0
        for unit in page.units:
            row = {
                "id": int(unit.id),
                "heading": str(unit.heading or "").strip(),
                "text": str(unit.text or "").strip(),
                "role": str(unit.role or "").strip(),
                "chars": int(unit.chars),
            }
            units.append(row)
            char_count += row["chars"]
        serialized.append(
            {
                "index": idx,
                "kind": str(page.kind),
                "title": str(page.title).strip(),
                "roles": list(page.roles),
                "char_count": char_count,
                "preview": _preview_text(" ".join(unit["text"] for unit in units if unit["text"])),
                "units": units,
            }
        )
    return serialized


def _apply_heading_anchored_titles(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    last_heading = ""
    for page in pages:
        headings = [str(unit.get("heading") or "").strip() for unit in page.get("units") or [] if str(unit.get("heading") or "").strip()]
        if headings:
            unique_headings: list[str] = []
            for heading in headings:
                if heading not in unique_headings:
                    unique_headings.append(heading)
            if len(unique_headings) == 1:
                page["title"] = unique_headings[0]
            else:
                page["title"] = " / ".join(unique_headings)
            last_heading = unique_headings[-1]
            continue
        if last_heading:
            page["title"] = f"{last_heading}（续）"
    return pages


def write_outline(layout: TopicLayout, plan: dict[str, Any]) -> Path:
    pages = plan.get("pages") or []
    lines = [
        "# 全局内容脚本",
        "",
        f"- 话题：{plan.get('title') or layout.root.name}",
        f"- 内容页数：{len([page for page in pages if page.get('kind') == 'content'])}",
        f"- 结尾页数：{len([page for page in pages if page.get('kind') == 'ending'])}",
        f"- 逻辑规划模式：{plan.get('logic_mode') or DEFAULT_LOGIC_MODE}",
        f"- LLM 回退：{'是' if plan.get('fallback_used') else '否'}",
        "",
        "## 封面",
        f"- 主题：{plan.get('title') or layout.root.name}",
        "- 用途：开头 3-5 秒，负责抛出整条内容的总爆点。",
        "",
    ]
    for page in pages:
        lines.append(f"## Page {int(page['index']):02d}")
        lines.append(f"- 类型：{page.get('kind')}")
        lines.append(f"- 主题：{page.get('title')}")
        roles = ", ".join(str(role) for role in page.get("roles") or [])
        lines.append(f"- 角色：{roles or '(none)'}")
        lines.append(f"- 预览：{page.get('preview') or ''}")
        source_text = _page_source_text(page)
        if source_text:
            lines.append("")
            lines.append(source_text)
        lines.append("")
    layout.outline_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return layout.outline_path


def save_plan(path: Path, plan: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_plan(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_content_plan(
    layout: TopicLayout,
    *,
    model_override: str = "",
    content_min_pages: int = DEFAULT_CONTENT_MIN_PAGES,
    content_max_pages: int = DEFAULT_CONTENT_MAX_PAGES,
    ending_policy: str = DEFAULT_ENDING_POLICY,
    logic_mode: str = DEFAULT_LOGIC_MODE,
    metadata_level: str = DEFAULT_METADATA_LEVEL,
) -> dict[str, Any]:
    core_note_text = layout.core_note_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not core_note_text:
        raise RuntimeError("core_note.md is empty")

    tmp_outline = layout.meta_dir / "_planner_outline.tmp.md"
    cover_prompt, series_prompts, pages, fallback_used = _build_bundle(
        article_text=core_note_text,
        article_title=layout.root.name if not core_note_text.startswith("# ") else core_note_text.splitlines()[0][2:].strip(),
        outline_output=tmp_outline,
        content_min_pages=content_min_pages,
        content_max_pages=content_max_pages,
        ending_policy=ending_policy,
        logic_mode=logic_mode,
        llm_model=model_override,
        include_cover=True,
        metadata_level=metadata_level,
    )
    if tmp_outline.exists():
        tmp_outline.unlink()

    title = layout.root.name
    for raw in core_note_text.splitlines():
        line = raw.strip()
        if line.startswith("# "):
            title = line[2:].strip() or title
            break

    serialized_pages = _apply_heading_anchored_titles(_serialize_pages(pages))

    plan = {
        "generated_at": now_iso(),
        "title": title,
        "logic_mode": logic_mode,
        "fallback_used": bool(fallback_used),
        "content_min_pages": int(content_min_pages),
        "content_max_pages": int(content_max_pages),
        "ending_policy": ending_policy,
        "metadata_level": metadata_level,
        "cover_prompt": cover_prompt or "",
        "series_prompts": series_prompts,
        "pages": serialized_pages,
    }
    write_outline(layout, plan)
    save_plan(layout.content_plan_path, plan)
    return plan
