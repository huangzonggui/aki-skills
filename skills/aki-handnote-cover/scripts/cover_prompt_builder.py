#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


COVER_CONSTRAINTS_PATH = Path(__file__).resolve().parents[1] / "references" / "constraints.md"
STYLE_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "aki-style-library"
    / "references"
    / "styles"
    / "手绘逻辑信息艺术设计师.md"
)
DEFAULT_VISUAL_ENFORCEMENT = (
    "Render Safety Rules:\n"
    "- Background must stay pure white (#FFFFFF), not cream, gray, paper texture, or notebook texture.\n"
    "- Keep every title, paragraph, icon, arrow, callout, and highlight inside a safety margin of at least 48px from all four edges on a 2K-class canvas.\n"
    "- If the layout gets crowded, reduce element size or split hierarchy, but do not let important content touch the edge."
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def build_handnote_cover_prompt(
    article_text: str,
    title: str = "",
    *,
    constraints_text: str = "",
    style_text: str = "",
) -> str:
    clean_article = article_text.strip()
    if not clean_article:
        raise ValueError("article_text is empty")

    parts = [
        constraints_text.strip() or _read_text(COVER_CONSTRAINTS_PATH),
        style_text.strip() or _read_text(STYLE_TEMPLATE_PATH),
        DEFAULT_VISUAL_ENFORCEMENT,
    ]
    if title.strip():
        parts.append(f"Title: {title.strip()}")
    parts.append("Article:\n" + clean_article)
    return "\n\n".join(parts).strip() + "\n"
