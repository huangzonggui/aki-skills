#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from content_plan import (
    DEFAULT_CONTENT_MAX_PAGES,
    DEFAULT_CONTENT_MIN_PAGES,
    build_content_plan,
    load_plan,
)
from llm_client import chat_complete
from state import BLOCKED, DONE, FAILED, RUNNING, first_incomplete_step, invalidate_from_step, load_state, set_artifact, set_step
from topic_layout import DEFAULT_RENDER_PLATFORMS_BY_MODE, IMAGE_PLATFORMS, VIDEO_PLATFORM_CONFIG, resolve_layout
from utils import (
    clear_directory,
    convert_image_to_jpg,
    ensure_dir,
    merge_text_files,
    preferred_image_for_stem,
    run,
    ts_label,
)


SCRIPT_DIR = Path(__file__).resolve().parent
BOOTSTRAP = SCRIPT_DIR / "bootstrap_topic.py"
COLLECT = SCRIPT_DIR / "collect_sources.py"
RENDER = SCRIPT_DIR / "render_images.py"
PUBLISH = SCRIPT_DIR / "publish_wechat_browser.py"
VIDEO = SCRIPT_DIR / "build_video_file.py"

SUMMARIZER_SKILL = Path(
    "/Users/aki/Development/code/aki-skills/skills/aki-text-note-summarizer/SKILL.md"
)
ADAPTIVE_SCRIPT = Path(
    "/Users/aki/Development/code/aki-skills/skills/aki-adaptive-video-script-style/scripts/generate_script.py"
)
DEFAULT_PUBLISH_PROFILE = Path(
    "/Users/aki/Library/Application Support/aki-skills/publisher-profiles/zimeiti-publisher"
)
GENERIC_HEADING_PREFIXES = (
    "我为什么关注",
    "我为什么特别关注",
    "它强在哪",
    "我的判断",
    "个人判断",
    "我的看法",
    "我的观点",
    "最后",
    "总结一下",
    "一个结论",
    "总结",
    "结论",
)
PROFILE_FILENAMES = ("Authors.com", "authors.com")
PERSONAL_NOTE_FILENAME = "个人笔记.md"
PRIVATE_STYLE_CONFIG_FILENAMES = ("writing_style_paths.local.json",)
PLATFORM_VIDEO_GUIDANCE = {
    "wechat": "平台是微信视频号。保留信息密度和判断感，别太像口号式短视频。",
    "xiaohongshu": "平台是小红书视频。语气更贴近真人分享，句子短一点，但不要装可爱。",
    "douyin": "平台是抖音。前两句更硬更快，结论更前置，少铺垫。",
}
IMAGEPOST_HASHTAG_PHRASES = (
    "AI应用",
    "大模型",
    "智能体",
    "Agent",
    "工作流",
    "AI工具",
    "OpenRouter",
    "OpenClaw",
    "ChatGPT",
    "Claude",
    "Gemini",
    "Kimi",
    "Qwen",
    "视频号",
    "公众号",
    "小红书",
    "抖音",
)

CORE_NOTE_APPROVAL_BLOCKED_MESSAGE = (
    "等待人工确认 core_note.md。请先查看 core_note.draft.md，整理并更新 core_note.md，"
    "再重新执行 approve_core_note。确认前不会继续生成 outline 和平台裂变内容。"
)


def _require_done(topic_root: Path, steps: list[str], hint: str = "") -> None:
    state = load_state(topic_root)
    missing = [name for name in steps if state["steps"][name]["status"] != DONE]
    if missing:
        suffix = f" {hint.strip()}" if hint else ""
        raise RuntimeError(f"Required step(s) not complete: {', '.join(missing)}.{suffix}")


def _run_python(script: Path, args: list[str]) -> int:
    cp = run(["python3", str(script), *args])
    if cp.stdout:
        print(cp.stdout.strip())
    if cp.stderr:
        print(cp.stderr.strip())
    return cp.returncode


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _core_note_signature(path: Path) -> dict[str, str | int]:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    return {
        "sha256": _sha256_text(text),
        "char_count": len(text),
    }


def _block_core_note_approval(topic_root: Path, layout, message: str, reason: str) -> None:
    invalidate_from_step(topic_root, "approve_core_note", reason=reason)
    set_step(
        topic_root,
        "approve_core_note",
        BLOCKED,
        message=message,
        meta={
            "draft_path": str(layout.core_note_draft_path),
            "core_note_path": str(layout.core_note_path),
        },
    )


def _ensure_core_note_approval_current(topic_root: Path, layout) -> None:
    state = load_state(topic_root)
    approval = state["steps"].get("approve_core_note", {})
    if approval.get("status") != DONE:
        return
    if not layout.core_note_path.exists():
        _block_core_note_approval(
            topic_root,
            layout,
            message="core_note.md 已缺失。请重新整理母稿后，再执行 approve_core_note。",
            reason="approved core_note.md is missing",
        )
        return
    approved_sha256 = str((approval.get("meta") or {}).get("approved_sha256") or "").strip()
    if not approved_sha256:
        _block_core_note_approval(
            topic_root,
            layout,
            message="这次批准记录早于新的母稿签名机制。请重新执行 approve_core_note，再继续生成 outline 和裂变内容。",
            reason="core note approval missing signature",
        )
        return
    current_signature = _core_note_signature(layout.core_note_path)
    if current_signature["sha256"] != approved_sha256:
        _block_core_note_approval(
            topic_root,
            layout,
            message="core_note.md 在批准后又被修改了。请重新确认母稿，并再次执行 approve_core_note。",
            reason="core note changed after approval",
        )


def _extract_summarizer_prompt() -> str:
    if not SUMMARIZER_SKILL.exists():
        return ""
    text = SUMMARIZER_SKILL.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"Use the following style guide.*?```([\s\S]*?)```", text)
    block = (match.group(1).strip() if match else "").strip()
    extra = ""
    extra_start = text.find("## Writing constraint")
    extra_end = text.find("## Workflow")
    if extra_start != -1 and extra_end != -1 and extra_end > extra_start:
        extra = text[extra_start:extra_end].strip()
    return "\n\n".join(part for part in [block, extra] if part).strip()


def _ensure_topic_root(topic_root: str) -> Path:
    path = Path(topic_root).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Topic root does not exist: {path}")
    return path


def _read_text_if_exists(path: Path | None) -> str:
    if not path or not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def _load_private_style_paths() -> list[Path]:
    raw_paths: list[str] = []
    config_paths: list[Path] = []
    for config_dir in [SUMMARIZER_SKILL.parent / "config", SCRIPT_DIR.parent / "config"]:
        for name in PRIVATE_STYLE_CONFIG_FILENAMES:
            config_paths.append(config_dir / name)
    env_config = os.getenv("AKI_WRITING_STYLE_CONFIG", "").strip()
    if env_config:
        config_paths.append(Path(env_config).expanduser())

    seen_configs: set[str] = set()
    for config_path in config_paths:
        key = str(config_path.resolve()) if config_path.exists() else str(config_path)
        if key in seen_configs or not config_path.exists() or not config_path.is_file():
            continue
        seen_configs.add(key)
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            raw_paths.extend(data.get("writing_style_paths") or data.get("paths") or [])
        except Exception:
            continue

    seen: set[str] = set()
    results: list[Path] = []
    for item in raw_paths:
        path = Path(str(item)).expanduser().resolve()
        key = str(path)
        if key in seen or not path.exists() or not path.is_file():
            continue
        seen.add(key)
        results.append(path)
    return results


def _find_profile_path(topic_root: Path) -> Path | None:
    candidates: list[Path] = []
    for folder in [topic_root, topic_root.parent]:
        for name in PROFILE_FILENAMES:
            candidates.append(folder / name)
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def _build_summary_context(topic_root: Path) -> str:
    layout = resolve_layout(topic_root)
    blocks: list[str] = []

    profile_path = _find_profile_path(topic_root)
    profile_text = _read_text_if_exists(profile_path)
    if profile_text:
        blocks.append(
            "## 用户画像（强约束）\n\n"
            "以下画像优先于默认写作口径。请按这份画像决定解释深度、术语密度和角度。\n\n"
            f"{profile_text}"
        )

    personal_note_text = _read_text_if_exists(layout.root / PERSONAL_NOTE_FILENAME)
    if personal_note_text:
        blocks.append(
            "## 用户亲自写的个人笔记（强约束）\n\n"
            "以下内容代表用户自己的灵感、关注点和判断。请优先吸收它的选题角度、冲突点和结论倾向。"
            "如果它与外部参考的事实口径冲突，事实仍以可验证资料为准，但主线和强调重点优先参考这份个人笔记。\n\n"
            f"{personal_note_text}"
        )

    for path in _load_private_style_paths():
        style_text = _read_text_if_exists(path)
        if not style_text:
            continue
        blocks.append(
            "## 私有写作风格（强约束）\n\n"
            "以下是用户自己的长期写作风格文档。请默认按它的读者画像、表达方式、事实纪律和术语策略来写。\n\n"
            f"{style_text}"
        )

    return "\n\n".join(blocks).strip()


def _normalize_heading_text(text: str) -> str:
    value = text.strip()
    value = re.sub(r"^\d+[\.、:：]\s*", "", value)
    value = re.sub(r"[\s\-—:：·\[\]()（）]+", "", value)
    return value


def _find_heading_issues(text: str) -> list[str]:
    issues: list[str] = []
    has_h1 = False
    for raw in text.splitlines():
        line = raw.strip()
        match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2).strip()
        normalized = _normalize_heading_text(title)
        if level == 1:
            has_h1 = True
        if level >= 2 and re.match(r"^\d+[\.、:：]\s*", title):
            issues.append(f"numbered heading: {title}")
        if any(normalized.startswith(prefix) for prefix in GENERIC_HEADING_PREFIXES):
            issues.append(f"generic heading: {title}")
    if not has_h1:
        issues.append("missing h1 title")
    return issues


def _rewrite_markdown_headings(text: str, model_override: str = "") -> str:
    issues = _find_heading_issues(text)
    if not issues:
        return text.strip()
    issue_text = "\n".join(f"- {item}" for item in issues)
    system_prompt = "你是中文内容编辑。你只负责修正 markdown 的标题结构，尤其是 H1/H2/H3。输出完整 markdown 成品，不要解释过程。"
    user_prompt = (
        "请修正下面这篇 markdown 的标题。\n"
        "发现的问题：\n"
        f"{issue_text}\n\n"
        "修正要求：\n"
        "1) 必须保留或补出一个 H1 标题；\n"
        "2) H1/H2/H3 必须从相邻正文里抽最强信息点，不要写结构标签；\n"
        "3) 禁止使用这些泛标题或其变体：我为什么特别关注、它强在哪、我的判断、个人判断、我的观点、最后、总结一下、一个结论、总结、结论；\n"
        "4) 默认不要使用 `## 1.` `## 2.` 这种编号式标题；\n"
        "5) 尽量只改标题，不改正文事实、段落顺序、列表内容；\n"
        "6) 输出仍然是完整 markdown。\n\n"
        "原文如下：\n\n"
        f"{text.strip()}\n"
    )
    revised = chat_complete(system_prompt, user_prompt, model_override=model_override, temperature=0.3)
    return revised.strip() or text.strip()


def _ensure_dynamic_headings(text: str, model_override: str = "") -> str:
    content = text.strip()
    if not content:
        return content
    for _ in range(2):
        issues = _find_heading_issues(content)
        if not issues:
            return content
        try:
            content = _rewrite_markdown_headings(content, model_override=model_override)
        except Exception:
            return content
    return content


def _compress_for_imagepost(text: str, max_chars: int = 320) -> str:
    blocks: list[str] = []
    current: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    if not blocks:
        return ""
    formatted = "\n\n".join(blocks).strip()
    if len(formatted) <= max_chars:
        return formatted
    kept: list[str] = []
    for block in blocks:
        candidate = "\n\n".join(kept + [block]).strip()
        if len(candidate) > max_chars:
            break
        kept.append(block)
    if kept:
        if len(kept) == len(blocks):
            return "\n\n".join(kept).strip()
        return "\n\n".join(kept).strip() + "\n\n…"
    return blocks[0][: max_chars - 1].rstrip() + "…"


def _build_imagepost_hashtags(title: str, body: str, limit: int = 4) -> str:
    return _build_imagepost_hashtags_with_fallback(title=title, body=body, limit=limit)


def _extract_json_array(text: str) -> list[str]:
    content = (text or "").strip()
    if not content:
        return []
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if fenced:
        content = fenced.group(1).strip()
    try:
        data = json.loads(content)
    except Exception:
        match = re.search(r"\[[\s\S]*\]", content)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except Exception:
            return []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()]


def _build_imagepost_hashtags_fallback(title: str, body: str, limit: int = 4) -> str:
    source = f"{title}\n{body[:1200]}".strip()
    tags: list[str] = []
    seen: set[str] = set()
    domain_tags = {"AI应用", "大模型", "智能体", "Agent", "AI工具"}

    def add(tag: str) -> None:
        clean = tag.strip().strip("#")
        if not clean or clean in seen:
            return
        seen.add(clean)
        tags.append(clean)

    for phrase in IMAGEPOST_HASHTAG_PHRASES:
        if phrase.lower() in source.lower():
            add(phrase)
        if len(tags) >= limit:
            break

    if len(tags) < limit and not any(tag in domain_tags for tag in tags):
        add("AI应用")

    if len(tags) < limit:
        for token in re.findall(r"\b[A-Z][A-Za-z0-9.+-]{1,30}\b", source):
            if any(ch.isdigit() for ch in token):
                continue
            add(token)
            if len(tags) >= limit:
                break

    if not tags:
        add("AI应用")
        add("内容创作")

    return " ".join(f"#{tag}" for tag in tags[:limit])


def _build_imagepost_hashtags_with_fallback(title: str, body: str, limit: int = 5, model_override: str = "") -> str:
    system_prompt = (
        "你是中文内容运营编辑。你的任务是基于文章内容，给微信公众号贴图生成更像真人会写的话题标签。"
        "优先考虑传播热度、搜索习惯和内容相关性。只输出 JSON 数组，不要解释。"
    )
    user_prompt = (
        f"请基于下面的标题和正文，生成 {limit} 个适合微信公众号贴图说明区的话题标签。\n\n"
        "要求：\n"
        "1) 输出 JSON 数组，数组长度必须等于指定数量；\n"
        "2) 每个元素不要带 #；\n"
        "3) 话题要兼顾 热度 + 准确性，不要全是品牌词，也不要全是空泛大词；\n"
        "4) 最多 2 个品牌/产品词，其余优先用赛道词、场景词、现象词；\n"
        "5) 不要出现重复、近义重复、过长短语；\n"
        "6) 默认面向中文 AI/科技内容读者。\n\n"
        f"标题：{title.strip()}\n\n"
        f"正文：\n{body[:2200].strip()}\n"
    )
    try:
        raw = chat_complete(system_prompt, user_prompt, model_override=model_override, temperature=0.6)
        tags = _extract_json_array(raw)
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in tags:
            clean = re.sub(r"^[#＃]+", "", item).strip()
            clean = re.sub(r"\s+", "", clean)
            if not clean or clean in seen:
                continue
            seen.add(clean)
            cleaned.append(clean)
            if len(cleaned) >= limit:
                break
        if len(cleaned) >= max(3, limit - 1):
            return " ".join(f"#{tag}" for tag in cleaned[:limit])
    except Exception:
        pass
    return _build_imagepost_hashtags_fallback(title, body, limit=limit)


def _build_wechat_imagepost_copy(title: str, body: str, model_override: str = "") -> str:
    compressed = _compress_for_imagepost(body)
    hashtags = _build_imagepost_hashtags_with_fallback(title, body, limit=5, model_override=model_override)
    blocks = [f"# {title}"]
    if compressed:
        blocks.extend(["", compressed])
    if hashtags:
        blocks.extend(["", hashtags])
    return "\n".join(blocks).strip() + "\n"


def _extract_h1_title(text: str, fallback: str) -> str:
    match = re.search(r"(?m)^#\s+(.+)$", text)
    if match:
        title = match.group(1).strip()
        if title:
            return title
    return fallback


def _strip_leading_h1(text: str) -> str:
    lines = text.splitlines()
    first_non_empty = -1
    for idx, line in enumerate(lines):
        if line.strip():
            first_non_empty = idx
            break
    if first_non_empty == -1:
        return ""
    if re.match(r"^#\s+.+$", lines[first_non_empty].strip()):
        lines = lines[:first_non_empty] + lines[first_non_empty + 1 :]
    return "\n".join(lines).strip()


def _relative_to_topic(topic_root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(topic_root.resolve()))


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


def _page_source_text(page: dict) -> str:
    blocks: list[str] = []
    for unit in page.get("units") or []:
        heading = str(unit.get("heading") or "").strip()
        text = str(unit.get("text") or "").strip()
        if heading:
            blocks.append(f"### {heading}\n{text}".strip())
        elif text:
            blocks.append(text)
    return "\n\n".join(part for part in blocks if part).strip()


def _estimate_segment_duration(segment_kind: str, char_count: int) -> float:
    if segment_kind == "cover":
        return 4.0
    base = max(7.0, min(18.0, round(char_count / 55.0, 1)))
    if segment_kind == "ending":
        return min(base, 10.0)
    return base


def _preferred_rendered_image(layout, platform: str, stem: str) -> Path:
    path = preferred_image_for_stem(layout.platform_images_dir(platform), stem)
    if not path:
        raise FileNotFoundError(f"Rendered image not found for {platform}: {stem}")
    return path


def _generate_segment_script(
    platform: str,
    title: str,
    segment_kind: str,
    theme: str,
    source_text: str,
    target_sec: int,
    model_override: str,
) -> str:
    if not ADAPTIVE_SCRIPT.exists():
        raise FileNotFoundError(f"Adaptive script generator missing: {ADAPTIVE_SCRIPT}")
    guidance = PLATFORM_VIDEO_GUIDANCE.get(platform, "")
    payload = (
        f"平台说明：{guidance}\n\n"
        f"全局标题：{title}\n"
        f"当前段落类型：{segment_kind}\n"
        f"当前段落主题：{theme}\n"
        f"目标时长：{target_sec} 秒\n\n"
        "请只围绕当前图片绑定的内容写这一段口播，不要抢后面图片的内容。\n\n"
        "当前段落素材如下：\n\n"
        f"{source_text.strip()}\n"
    ).strip()
    with tempfile.TemporaryDirectory(prefix=f"aki-pipeline-{platform}-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        in_path = tmp_path / "segment_input.md"
        out_path = tmp_path / "segment_output.md"
        in_path.write_text(payload + "\n", encoding="utf-8")
        min_sec = max(3, target_sec - 2)
        max_sec = max(min_sec + 1, target_sec + 2)
        cmd = [
            "python3",
            str(ADAPTIVE_SCRIPT),
            "--input",
            str(in_path),
            "--output",
            str(out_path),
            "--min-sec",
            str(min_sec),
            "--max-sec",
            str(max_sec),
            "--target-sec",
            str(target_sec),
            "--source-label",
            VIDEO_PLATFORM_CONFIG[platform]["adaptive_source_label"],
        ]
        if model_override:
            cmd.extend(["--model", model_override])
        cp = run(cmd)
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr.strip() or cp.stdout.strip() or "adaptive video script generation failed")
        text = out_path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            raise RuntimeError("Adaptive video script generator returned empty content")
        return text


def intent_init_topic(args: argparse.Namespace) -> int:
    cmd = [
        "--cwd",
        args.cwd,
        "--title",
        args.title,
        "--mode",
        args.mode,
        "--timestamp",
        args.timestamp or ts_label(),
    ]
    return _run_python(BOOTSTRAP, cmd)


def intent_ingest_sources(args: argparse.Namespace) -> int:
    topic_root = _ensure_topic_root(args.topic_root)
    _require_done(topic_root, ["init_topic"], hint="Run init_topic first.")
    cmd = ["--topic-root", str(topic_root)]
    for item in args.source:
        cmd.extend(["--source", item])
    if args.wechat_fetcher:
        cmd.extend(["--wechat-fetcher", args.wechat_fetcher])
    if args.youtube_runner:
        cmd.extend(["--youtube-runner", args.youtube_runner])
    if args.youtube_download_script:
        cmd.extend(["--youtube-download-script", args.youtube_download_script])
    return _run_python(COLLECT, cmd)


def intent_summarize_core_note(args: argparse.Namespace) -> int:
    topic_root = _ensure_topic_root(args.topic_root)
    layout = resolve_layout(topic_root)
    _require_done(topic_root, ["ingest_sources"], hint="Collect refs before summarizing core note.")
    refs = sorted(layout.refs_dir.glob("*_clean.md"))
    if not refs:
        raise RuntimeError("No clean reference files found under refs/")
    merged = merge_text_files(refs)
    if not merged:
        raise RuntimeError("Clean refs are empty")

    set_step(topic_root, "summarize_core_note", "running", message="Generating core note draft from refs")
    prompt_block = _extract_summarizer_prompt()
    system_prompt = "你是 Aki 的内容助手。请严格按给定风格产出“个人核心笔记”初稿。输出只要 markdown 正文，不要解释过程。"
    if prompt_block:
        system_prompt += "\n\n以下为已接入的 aki-text-note-summarizer 风格约束：\n\n" + prompt_block

    user_prompt = (
        "请基于以下资料生成一篇“核心个人笔记”初稿。\n"
        "要求：\n"
        "1) 保留个人观点空间，避免平铺复述；\n"
        "2) 结构清晰，适合后续裂变到公众号/小红书/视频；\n"
        "3) 默认中文输出；\n"
        "4) 默认面向普通非技术用户，少用技术黑话；\n"
        "5) 像 Computer Use、Agent、Context Window 这类词，第一次出现时优先换成大众说法，或立刻补一句白话解释；\n"
        "6) GPT、ChatGPT、OpenClaw、Dexy、Claude、Codex 这类知名产品名可以直接保留；\n"
        "7) 不要捏造数字、百分比、榜单排名、测试结果。资料里没有明确给出的，宁可不写；\n"
        "8) 默认先把最重要的信息点讲清楚，再展开判断。优先交代“谁做的、产品叫什么、现在是什么状态、为什么值得关注”；\n"
        "9) 如果选题本身就是一个单一信息点，不要为了显得完整而硬写成长解释文，宁可短一点、准一点；\n"
        "10) 避免模板化表达，不要频繁使用“真正的变化”“最后该记住的结论”这类空泛结构句；\n"
        "11) 标题和小标题尽量具体，段落尽量短。若用户的个人笔记已经给了结构，就优先服从个人笔记。\n\n"
    )
    extra_context = _build_summary_context(topic_root)
    if extra_context:
        user_prompt += "以下是必须吸收的额外上下文：\n\n" + extra_context + "\n\n"
    user_prompt += "资料如下：\n\n" + merged + "\n"

    try:
        content = chat_complete(system_prompt, user_prompt, model_override=args.model)
        content = _ensure_dynamic_headings(content, model_override=args.model)
        layout.core_note_draft_path.write_text(content.strip() + "\n", encoding="utf-8")
        _block_core_note_approval(
            topic_root,
            layout,
            message=CORE_NOTE_APPROVAL_BLOCKED_MESSAGE,
            reason="core note draft regenerated",
        )
        set_step(
            topic_root,
            "summarize_core_note",
            DONE,
            message="Core note draft generated",
            meta={
                "draft_path": str(layout.core_note_draft_path),
            },
        )
        print(str(layout.core_note_draft_path))
        return 0
    except Exception as exc:
        set_step(topic_root, "summarize_core_note", FAILED, message=str(exc))
        raise


def intent_co_create_core_note(args: argparse.Namespace) -> int:
    topic_root = _ensure_topic_root(args.topic_root)
    layout = resolve_layout(topic_root)
    _require_done(topic_root, ["summarize_core_note"], hint="Run summarize_core_note first.")
    if not layout.core_note_draft_path.exists():
        raise FileNotFoundError(f"core_note.draft.md not found: {layout.core_note_draft_path}")
    if not layout.core_note_path.exists():
        draft_text = layout.core_note_draft_path.read_text(encoding="utf-8", errors="ignore").strip()
        if not draft_text:
            raise RuntimeError("core_note.draft.md is empty")
        layout.core_note_path.write_text(draft_text + "\n", encoding="utf-8")
    _block_core_note_approval(
        topic_root,
        layout,
        message=CORE_NOTE_APPROVAL_BLOCKED_MESSAGE,
        reason="entered core note co-creation/editing stage",
    )
    print(str(layout.core_note_path))
    return 2


def intent_approve_core_note(args: argparse.Namespace) -> int:
    topic_root = _ensure_topic_root(args.topic_root)
    layout = resolve_layout(topic_root)
    _require_done(topic_root, ["summarize_core_note"], hint="Run summarize_core_note first.")
    if not layout.core_note_path.exists():
        raise FileNotFoundError(f"core_note.md not found: {layout.core_note_path}. Run co_create_core_note first.")
    text = layout.core_note_path.read_text(encoding="utf-8", errors="ignore").strip()
    if len(text) < 120:
        raise RuntimeError("core_note.md is too short; please revise before approval")
    signature = _core_note_signature(layout.core_note_path)
    invalidate_from_step(topic_root, "derive_platform_copies", reason="core note approved/updated")
    set_step(
        topic_root,
        "approve_core_note",
        DONE,
        message="母稿已人工确认，现在可以继续生成 outline 和平台文案",
        meta={
            "draft_path": str(layout.core_note_draft_path),
            "core_note_path": str(layout.core_note_path),
            "approved_sha256": signature["sha256"],
            "approved_char_count": signature["char_count"],
        },
    )
    set_artifact(topic_root, "approved_core_note_sha256", signature["sha256"])
    return 0


def intent_derive_platform_copies(args: argparse.Namespace) -> int:
    topic_root = _ensure_topic_root(args.topic_root)
    layout = resolve_layout(topic_root)
    _ensure_core_note_approval_current(topic_root, layout)
    _require_done(topic_root, ["approve_core_note"], hint="Approve core note before deriving copies.")
    if not layout.core_note_path.exists():
        raise FileNotFoundError(f"core_note.md not found: {layout.core_note_path}")

    text = layout.core_note_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        raise RuntimeError("core_note.md is empty")

    set_step(topic_root, "derive_platform_copies", RUNNING, message="Planning unified outline and platform copies")
    try:
        plan = build_content_plan(
            layout,
            model_override=args.model,
            content_min_pages=args.content_min_pages,
            content_max_pages=args.content_max_pages,
            ending_policy=args.ending_policy,
            logic_mode=args.logic_mode,
        )

        layout.wechat_article_path.write_text(text + "\n", encoding="utf-8")

        imagepost_title = _extract_h1_title(text, fallback=plan.get("title") or "微信图文")
        imagepost_body = _strip_leading_h1(text)
        layout.wechat_imagepost_copy_path.write_text(
            _build_wechat_imagepost_copy(imagepost_title, imagepost_body, model_override=args.model),
            encoding="utf-8",
        )

        outline_blocks = []
        for page in plan.get("pages") or []:
            outline_blocks.append(
                f"## {int(page['index']):02d}. {page['title']}\n\n"
                f"类型：{page['kind']}\n\n"
                f"素材：\n\n{_page_source_text(page)}"
            )
        outline_brief = "\n\n".join(outline_blocks).strip()
        xhs_prompt = (
            "你是小红书图文文案助手。请基于统一分页结果生成一版图文稿。\n\n"
            "硬性要求：\n"
            f"1) 必须严格按统一页序输出 {len(plan.get('pages') or [])} 个 H2 小节，顺序不能乱。\n"
            "2) 第一行只能是一个 H1 标题。\n"
            "3) 每个 H2 小节对应一张图的主题，不要再自行增加或减少页数。\n"
            "4) 语言更口语，但不要撒娇，不要模板化收口，不要输出话题标签。\n"
            "5) 专业词先翻成人话。\n\n"
            f"全局标题：{plan.get('title')}\n\n"
            f"统一分页结果：\n\n{outline_brief}\n\n"
            f"核心母稿：\n\n{text}\n"
        )
        try:
            xhs_text = chat_complete(
                "你是小红书图文文案助手。你只输出 markdown 成稿，不解释。",
                xhs_prompt,
                model_override=args.model,
                temperature=0.7,
            )
        except Exception:
            fallback_sections = [f"## {page['title']}\n\n{page['preview']}" for page in plan.get("pages") or []]
            xhs_text = f"# {plan.get('title') or imagepost_title}\n\n" + "\n\n".join(fallback_sections) + "\n"
        layout.xiaohongshu_post_path.write_text(xhs_text.strip() + "\n", encoding="utf-8")

        invalidate_from_step(topic_root, "generate_prompts", reason="outline and copies regenerated")
        set_artifact(topic_root, "content_plan", str(layout.content_plan_path))
        set_artifact(topic_root, "outline", str(layout.outline_path))
        set_step(
            topic_root,
            "derive_platform_copies",
            DONE,
            message="Unified outline and platform copies generated",
            meta={
                "outline_path": str(layout.outline_path),
                "content_plan_path": str(layout.content_plan_path),
                "wechat_article": str(layout.wechat_article_path),
                "wechat_imagepost": str(layout.wechat_imagepost_copy_path),
                "xhs_copy": str(layout.xiaohongshu_post_path),
            },
        )
        print(str(layout.outline_path))
        return 0
    except Exception as exc:
        set_step(topic_root, "derive_platform_copies", FAILED, message=str(exc))
        raise


def intent_generate_prompts(args: argparse.Namespace) -> int:
    topic_root = _ensure_topic_root(args.topic_root)
    _ensure_core_note_approval_current(topic_root, resolve_layout(topic_root))
    _require_done(topic_root, ["derive_platform_copies"], hint="Generate unified outline and copies first.")
    mode = load_state(topic_root).get("mode", args.mode)
    return _run_python(RENDER, ["--topic-root", str(topic_root), "--mode", mode, "--stage", "prompts"])


def intent_render_images(args: argparse.Namespace) -> int:
    topic_root = _ensure_topic_root(args.topic_root)
    _ensure_core_note_approval_current(topic_root, resolve_layout(topic_root))
    _require_done(topic_root, ["generate_prompts"], hint="Run generate_prompts first.")
    mode = load_state(topic_root).get("mode", args.mode)
    cmd = [
        "--topic-root",
        str(topic_root),
        "--mode",
        mode,
        "--stage",
        "render",
        "--approved-titles",
        "--platforms",
        args.platforms or "auto",
    ]
    if args.unit_cost is not None:
        cmd.extend(["--unit-cost", str(args.unit_cost)])
    return _run_python(RENDER, cmd)


def intent_derive_video_scripts(args: argparse.Namespace) -> int:
    topic_root = _ensure_topic_root(args.topic_root)
    layout = resolve_layout(topic_root)
    _ensure_core_note_approval_current(topic_root, layout)
    _require_done(topic_root, ["derive_platform_copies", "render_images"], hint="Need outline and rendered images.")
    plan = load_plan(layout.content_plan_path)
    mode = load_state(topic_root).get("mode", args.mode)
    platforms = _parse_platforms(args.platforms, mode)

    set_step(topic_root, "derive_video_scripts", RUNNING, message=f"Generating bound video scripts for {', '.join(platforms)}")
    try:
        for platform in platforms:
            platform_dir = layout.video_platform_dir(platform)
            platform_dir.mkdir(parents=True, exist_ok=True)
            segments: list[dict] = []
            cover_image = _preferred_rendered_image(layout, platform, "cover_01")
            cover_source = (
                f"封面图绑定整条内容的总标题：{plan.get('title')}\n\n"
                f"全局分页预览：\n" + "\n".join(
                    f"- Page {int(page['index']):02d}: {page['title']}" for page in (plan.get('pages') or [])
                )
            )
            cover_duration = int(round(_estimate_segment_duration("cover", 0)))
            cover_script = _generate_segment_script(
                platform=platform,
                title=str(plan.get("title") or layout.root.name),
                segment_kind="cover",
                theme=str(plan.get("title") or layout.root.name),
                source_text=cover_source,
                target_sec=cover_duration,
                model_override=args.model,
            )
            segments.append(
                {
                    "slot": 1,
                    "image_key": "cover_01",
                    "image_path": str(cover_image),
                    "image_relative": _relative_to_topic(topic_root, cover_image),
                    "kind": "cover",
                    "theme": str(plan.get("title") or layout.root.name),
                    "duration_sec": float(cover_duration),
                    "script": cover_script,
                }
            )

            for page in plan.get("pages") or []:
                stem = f"series_{int(page['index']):02d}"
                image_path = _preferred_rendered_image(layout, platform, stem)
                duration = int(round(_estimate_segment_duration(str(page.get("kind") or "content"), int(page.get("char_count") or 0))))
                source_text = (
                    f"页面主题：{page['title']}\n"
                    f"页面角色：{', '.join(page.get('roles') or [])}\n\n"
                    f"页面素材：\n\n{_page_source_text(page)}"
                )
                script_text = _generate_segment_script(
                    platform=platform,
                    title=str(plan.get("title") or layout.root.name),
                    segment_kind=str(page.get("kind") or "content"),
                    theme=str(page.get("title") or ""),
                    source_text=source_text,
                    target_sec=duration,
                    model_override=args.model,
                )
                segments.append(
                    {
                        "slot": len(segments) + 1,
                        "image_key": stem,
                        "image_path": str(image_path),
                        "image_relative": _relative_to_topic(topic_root, image_path),
                        "kind": str(page.get("kind") or "content"),
                        "theme": str(page.get("title") or ""),
                        "duration_sec": float(duration),
                        "script": script_text,
                        "page_index": int(page["index"]),
                    }
                )

            timeline = {
                "generated_at": ts_label(),
                "platform": platform,
                "title": str(plan.get("title") or layout.root.name),
                "segments": segments,
                "total_duration_sec": round(sum(float(segment["duration_sec"]) for segment in segments), 1),
            }
            layout.video_timeline_path(platform).write_text(
                json.dumps(timeline, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            header = f"# {VIDEO_PLATFORM_CONFIG[platform]['label']} 口播脚本\n\n"
            blocks: list[str] = [header.rstrip()]
            for segment in segments:
                blocks.append(f"## {int(segment['slot']):02d}. {segment['image_key']}")
                blocks.append(f"- 图片：{segment['image_relative']}")
                blocks.append(f"- 类型：{segment['kind']}")
                blocks.append(f"- 主题：{segment['theme']}")
                blocks.append(f"- 建议时长：{segment['duration_sec']}s")
                blocks.append("")
                blocks.append(str(segment["script"]).strip())
                blocks.append("")
            layout.video_voice_script_path(platform).write_text("\n".join(blocks).strip() + "\n", encoding="utf-8")
            set_artifact(topic_root, f"video_timeline_{platform}", str(layout.video_timeline_path(platform)))
            set_artifact(topic_root, f"video_script_{platform}", str(layout.video_voice_script_path(platform)))

        invalidate_from_step(topic_root, "build_video_package", reason="video scripts regenerated")
        set_step(
            topic_root,
            "derive_video_scripts",
            DONE,
            message="Bound video scripts generated",
            meta={"platforms": platforms},
        )
        print(json.dumps({platform: str(layout.video_voice_script_path(platform)) for platform in platforms}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        set_step(topic_root, "derive_video_scripts", FAILED, message=str(exc))
        raise


def intent_publish_wechat_drafts(args: argparse.Namespace) -> int:
    topic_root = _ensure_topic_root(args.topic_root)
    layout = resolve_layout(topic_root)
    _ensure_core_note_approval_current(topic_root, layout)
    _require_done(topic_root, ["derive_platform_copies", "render_images"], hint="Need copies and rendered images.")

    layout.publish_images_dir.mkdir(parents=True, exist_ok=True)
    clear_directory(layout.publish_images_dir)
    ordered: list[Path] = []
    cover = preferred_image_for_stem(layout.platform_images_dir("wechat"), "cover_01")
    if cover:
        ordered.append(cover)
    for idx in range(1, 100):
        image = preferred_image_for_stem(layout.platform_images_dir("wechat"), f"series_{idx:02d}")
        if not image:
            break
        ordered.append(image)
    if not ordered:
        raise RuntimeError("No rendered WeChat images found for publishing")

    for idx, src in enumerate(ordered, start=1):
        dst = layout.publish_images_dir / f"{idx:02d}.jpg"
        if src.suffix.lower() in {".jpg", ".jpeg"}:
            shutil.copy2(src, dst)
        else:
            convert_image_to_jpg(src, dst)

    cmd = [
        "--topic-root",
        str(topic_root),
        "--article-markdown",
        _relative_to_topic(topic_root, layout.wechat_article_path),
        "--imagepost-markdown",
        _relative_to_topic(topic_root, layout.wechat_imagepost_copy_path),
        "--images-dir",
        _relative_to_topic(topic_root, layout.publish_images_dir),
        "--only",
        args.publish_only,
        "--profile",
        args.profile or str(DEFAULT_PUBLISH_PROFILE),
    ]
    if args.article_style:
        cmd.extend(["--article-style", args.article_style])
    if args.publish_dry_run:
        cmd.append("--dry-run")
    return _run_python(PUBLISH, cmd)


def intent_build_video_package(args: argparse.Namespace) -> int:
    topic_root = _ensure_topic_root(args.topic_root)
    _ensure_core_note_approval_current(topic_root, resolve_layout(topic_root))
    _require_done(topic_root, ["derive_video_scripts"], hint="Generate timeline and voice scripts first.")
    mode = load_state(topic_root).get("mode", args.mode)
    cmd = [
        "--topic-root",
        str(topic_root),
        "--mode",
        mode,
        "--platforms",
        args.platforms or "auto",
        "--res",
        "1080",
        "--fps",
        "30",
    ]
    if args.voice_name:
        cmd.extend(["--voice-name", args.voice_name])
    cmd.extend(["--speed-override", str(args.voice_speed)])
    if args.force_export:
        cmd.append("--force-export")
    return _run_python(VIDEO, cmd)


def intent_resume(args: argparse.Namespace) -> int:
    topic_root = _ensure_topic_root(args.topic_root)
    _ensure_core_note_approval_current(topic_root, resolve_layout(topic_root))
    state = load_state(topic_root)
    nxt = first_incomplete_step(state)
    if not nxt:
        print("All steps are complete.")
        return 0
    print(f"Next step: {nxt}")
    print(f"Current status: {state['steps'][nxt]['status']}")
    message = str(state["steps"][nxt].get("message") or "").strip()
    if message:
        print(f"Message: {message}")
    if nxt == "approve_core_note":
        print("Hint: 先检查 core_note.draft.md；如还没建母稿，可先运行 --intent co_create_core_note；确认 core_note.md 后再运行 --intent approve_core_note")
    else:
        print(f"Hint: run --intent {nxt}")
    return 0


def intent_rework(args: argparse.Namespace) -> int:
    topic_root = _ensure_topic_root(args.topic_root)
    layout = resolve_layout(topic_root)
    target = args.target.strip()
    if target in {"从上次中断继续", "resume", "继续", "continue"}:
        return intent_resume(args)

    aliases = {
        "返工核心笔记": "core_note",
        "返工统一分页": "outline",
        "返工提示词": "prompts",
        "返工图片": "images",
        "返工视频脚本": "video_scripts",
        "返工视频": "video",
    }
    normalized = aliases.get(target, target)
    mapping = {
        "core_note": "summarize_core_note",
        "outline": "derive_platform_copies",
        "prompts": "generate_prompts",
        "images": "render_images",
        "video_scripts": "derive_video_scripts",
        "video": "build_video_package",
    }
    step = mapping.get(normalized)
    if not step:
        raise ValueError(f"Unknown rework target: {target}")
    invalidate_from_step(topic_root, step, reason=f"rework target={normalized}")

    cleanup: list[Path] = []
    if normalized == "core_note":
        cleanup.extend(
            [
                layout.core_note_draft_path,
                layout.core_note_path,
                layout.outline_path,
                layout.content_plan_path,
                layout.copies_dir,
                layout.prompts_dir,
                layout.images_dir,
                layout.video_dir,
            ]
        )
    elif normalized == "outline":
        cleanup.extend([layout.outline_path, layout.content_plan_path, layout.copies_dir, layout.prompts_dir, layout.images_dir, layout.video_dir])
    elif normalized == "prompts":
        cleanup.extend([layout.prompts_dir, layout.prompt_review_path, layout.images_dir, layout.video_dir])
    elif normalized == "images":
        cleanup.extend([layout.images_dir, layout.image_cost_summary_md, layout.image_cost_summary_json, layout.video_dir])
    elif normalized == "video_scripts":
        cleanup.extend([layout.video_dir])
    elif normalized == "video":
        for platform in VIDEO_PLATFORM_CONFIG:
            cleanup.extend([layout.video_output_dir(platform), layout.video_stage_dir(platform)])

    for path in cleanup:
        if not path.exists():
            continue
        if path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
    layout.ensure_structure()
    print(f"Rework prepared for target: {normalized}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Intent-based pipeline controller for aki-content-pipeline-pro")
    parser.add_argument(
        "--intent",
        required=True,
        choices=[
            "init_topic",
            "ingest_sources",
            "summarize_core_note",
            "co_create_core_note",
            "approve_core_note",
            "derive_platform_copies",
            "generate_prompts",
            "render_images",
            "derive_video_scripts",
            "publish_wechat_drafts",
            "build_video_package",
            "resume",
            "continue_from_last",
            "rework",
        ],
    )
    parser.add_argument("--topic-root", default="")
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--title", default="")
    parser.add_argument("--mode", choices=["prod", "test"], default="prod")
    parser.add_argument("--timestamp", default="")
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--wechat-fetcher", default="")
    parser.add_argument("--youtube-runner", default="")
    parser.add_argument("--youtube-download-script", default="")
    parser.add_argument("--approved-prompt-titles", action="store_true")
    parser.add_argument("--profile", default="")
    parser.add_argument("--publish-only", choices=["article", "imagepost", "both"], default="article")
    parser.add_argument("--publish-dry-run", action="store_true")
    parser.add_argument("--article-style", default="")
    parser.add_argument("--voice-name", default="日常松弛男")
    parser.add_argument("--voice-speed", type=float, default=1.2)
    parser.add_argument("--force-export", action="store_true")
    parser.add_argument("--platforms", default="auto")
    parser.add_argument("--target", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--content-min-pages", type=int, default=DEFAULT_CONTENT_MIN_PAGES)
    parser.add_argument("--content-max-pages", type=int, default=DEFAULT_CONTENT_MAX_PAGES)
    parser.add_argument("--ending-policy", choices=["adaptive", "always", "never"], default="adaptive")
    parser.add_argument("--logic-mode", choices=["hybrid", "rule", "llm"], default="hybrid")
    parser.add_argument("--unit-cost", type=float, default=0.6)
    args = parser.parse_args()

    if args.intent == "init_topic":
        if not args.title.strip():
            raise ValueError("--title is required for init_topic")
        return intent_init_topic(args)
    if not args.topic_root:
        raise ValueError("--topic-root is required for this intent")

    if args.intent == "ingest_sources":
        if not args.source:
            raise ValueError("--source is required for ingest_sources")
        return intent_ingest_sources(args)
    if args.intent == "summarize_core_note":
        return intent_summarize_core_note(args)
    if args.intent == "co_create_core_note":
        return intent_co_create_core_note(args)
    if args.intent == "approve_core_note":
        return intent_approve_core_note(args)
    if args.intent == "derive_platform_copies":
        return intent_derive_platform_copies(args)
    if args.intent == "generate_prompts":
        return intent_generate_prompts(args)
    if args.intent == "render_images":
        if not args.approved_prompt_titles:
            raise ValueError("render_images requires --approved-prompt-titles")
        return intent_render_images(args)
    if args.intent == "derive_video_scripts":
        return intent_derive_video_scripts(args)
    if args.intent == "publish_wechat_drafts":
        return intent_publish_wechat_drafts(args)
    if args.intent == "build_video_package":
        return intent_build_video_package(args)
    if args.intent == "resume":
        return intent_resume(args)
    if args.intent == "continue_from_last":
        return intent_resume(args)
    if args.intent == "rework":
        if not args.target:
            raise ValueError("--target is required for rework")
        return intent_rework(args)
    raise RuntimeError(f"Unsupported intent: {args.intent}")


if __name__ == "__main__":
    raise SystemExit(main())
