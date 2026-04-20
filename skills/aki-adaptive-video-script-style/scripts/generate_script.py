#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(os.getenv("AKI_SKILLS_REPO_ROOT", "")).expanduser().resolve() if os.getenv("AKI_SKILLS_REPO_ROOT") else SCRIPT_DIR.parents[2]
SHARED_DIR = REPO_ROOT / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from aki_runtime import default_ai_keys_env_path, default_private_script_asset_root  # noqa: E402


COMFLY_CONFIG = Path.home() / ".config" / "comfly" / "config"
KEYS_ENV = default_ai_keys_env_path()
DEFAULT_BASE = "https://ai.comfly.chat"
CHAT_PATH = "/v1/chat/completions"
DEFAULT_MODEL = "gemini-3-pro-preview-thinking"
FALLBACK_MODEL = "gpt-5-chat-latest"
STYLE_REF = SCRIPT_DIR.parents[1] / "references" / "style-rules.md"
PRIVATE_SCRIPT_ASSET_ROOT = default_private_script_asset_root()
PRIVATE_SCRIPT_RULE_FILES = ("个人口播偏好.md", "script_preferences.md")
PRIVATE_SCRIPT_SAMPLE_DIRS = ("style_samples", "current_topic_refs")
PRIVATE_SCRIPT_SAMPLE_LIMIT = 5
PRIVATE_SCRIPT_SAMPLE_CHAR_LIMIT = 5000
PRIVATE_SCRIPT_SAMPLE_FILE_CHAR_LIMIT = 1200


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        out[key] = value.strip().strip("'\"")
    return out


def _normalize_chat_url(raw: str) -> str:
    value = raw.strip() or DEFAULT_BASE
    if value.endswith(CHAT_PATH):
        return value
    return value.rstrip("/") + CHAT_PATH


def resolve_config(model_override: str = "") -> dict[str, str]:
    cfg_file = _parse_env_file(COMFLY_CONFIG)
    keys_file = _parse_env_file(KEYS_ENV)

    api_key = (
        os.getenv("COMFLY_API_KEY")
        or keys_file.get("COMFLY_API_KEY")
        or cfg_file.get("COMFLY_API_KEY")
        or cfg_file.get("API_KEY")
        or ""
    ).strip()
    if not api_key:
        raise RuntimeError(
            f"Missing COMFLY_API_KEY (env / {KEYS_ENV} / {COMFLY_CONFIG})"
        )

    raw_url = (
        os.getenv("COMFLY_API_URL")
        or keys_file.get("COMFLY_API_URL")
        or cfg_file.get("COMFLY_API_URL")
        or os.getenv("COMFLY_API_BASE_URL")
        or keys_file.get("COMFLY_API_BASE_URL")
        or cfg_file.get("COMFLY_API_BASE_URL")
        or ""
    ).strip()
    api_url = _normalize_chat_url(raw_url)

    model = (
        model_override.strip()
        or os.getenv("COMFLY_CHAT_MODEL")
        or keys_file.get("COMFLY_CHAT_MODEL")
        or os.getenv("COMFLY_MODEL")
        or keys_file.get("COMFLY_MODEL")
        or cfg_file.get("COMFLY_CHAT_MODEL")
        or cfg_file.get("COMFLY_MODEL")
        or DEFAULT_MODEL
    ).strip()

    return {"api_key": api_key, "api_url": api_url, "model": model}


def chat_complete(
    system_prompt: str,
    user_prompt: str,
    model_override: str = "",
    temperature: float = 0.65,
) -> str:
    cfg = resolve_config(model_override)
    payload: dict[str, Any] = {
        "model": cfg["model"],
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    req = Request(
        url=cfg["api_url"],
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
            "User-Agent": "aki-adaptive-video-script-style/1.0",
        },
    )
    with urlopen(req, timeout=180) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Empty chat response: {raw[:400]}")
    content = (((choices[0] or {}).get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("Chat response contains empty content")
    return content


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def _strip_markdown_noise(text: str) -> str:
    body = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line:
            lines.append("")
            continue
        if line.startswith("```"):
            continue
        if re.match(r"^\s*-{3,}\s*$", line):
            lines.append("")
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^[-*•]\s*", "", line)
        line = re.sub(r"^\d+[\.、]\s*", "", line)
        line = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _estimate_target_seconds(text: str, min_sec: int, max_sec: int) -> int:
    body = _strip_markdown_noise(text)
    size = len(body)
    if size <= 220:
        guess = 20
    elif size <= 450:
        guess = 35
    elif size <= 900:
        guess = 60
    elif size <= 1600:
        guess = 110
    elif size <= 2600:
        guess = 180
    else:
        guess = 260
    return max(min_sec, min(max_sec, guess))


def _target_char_range(seconds: int) -> tuple[int, int]:
    # Chinese short-form speaking often lands around 2.8-4.3 chars/sec.
    return int(seconds * 2.8), int(seconds * 4.3)


def _spoken_clip(text: str, max_chars: int = 60) -> str:
    s = re.sub(r"\s+", " ", text).strip()
    if not s:
        return ""
    s = re.sub(r"^[一二三四五六七八九十]+[\.、]\s*", "", s)
    parts = re.split(r"[。！？；]", s, maxsplit=1)
    if parts and parts[0].strip():
        s = parts[0].strip()
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"


def _preferred_point_count(target_sec: int) -> int:
    if target_sec <= 30:
        return 2
    if target_sec <= 90:
        return 3
    return 4


def _iter_private_sample_paths() -> list[Path]:
    if not PRIVATE_SCRIPT_ASSET_ROOT.exists():
        return []

    paths: list[Path] = []
    for dirname in PRIVATE_SCRIPT_SAMPLE_DIRS:
        folder = PRIVATE_SCRIPT_ASSET_ROOT / dirname
        if not folder.exists() or not folder.is_dir():
            continue
        paths.extend(
            sorted(
                folder.glob("*.md"),
                key=lambda p: (p.stat().st_mtime, p.name),
                reverse=True,
            )
        )

    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
        if len(result) >= PRIVATE_SCRIPT_SAMPLE_LIMIT:
            break
    return result


def _read_private_script_examples() -> str:
    parts: list[str] = []
    total = 0
    for path in _iter_private_sample_paths():
        try:
            text = _read_text(path)
        except Exception:
            continue
        if not text:
            continue
        excerpt = text.strip()
        if len(excerpt) > PRIVATE_SCRIPT_SAMPLE_FILE_CHAR_LIMIT:
            excerpt = excerpt[: PRIVATE_SCRIPT_SAMPLE_FILE_CHAR_LIMIT - 1].rstrip() + "…"
        block = f"## 私有样本：{path.stem}\n\n{excerpt}"
        if total + len(block) > PRIVATE_SCRIPT_SAMPLE_CHAR_LIMIT and parts:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts).strip()


def _read_private_script_rules() -> str:
    parts: list[str] = []
    for name in PRIVATE_SCRIPT_RULE_FILES:
        path = PRIVATE_SCRIPT_ASSET_ROOT / name
        if not path.exists() or not path.is_file():
            continue
        try:
            text = _read_text(path)
        except Exception:
            continue
        if not text:
            continue
        parts.append(text)
    return "\n\n".join(parts).strip()


def _normalize_fallback_line(line: str) -> str:
    s = line.strip()
    if not s:
        return ""
    if re.match(r"^(平台说明|当前段落类型|目标时长|来源标识|当前段落素材如下)\s*[:：]", s):
        return ""
    if re.match(r"^全局分页预览\s*[:：]?$", s):
        return ""
    if s.startswith("请只围绕当前图片绑定的内容写这一段口播"):
        return ""
    page_match = re.match(r"^Page\s*\d+\s*[:：]\s*(.+)$", s, flags=re.IGNORECASE)
    if page_match:
        return page_match.group(1).strip()
    if re.match(r"^(全局标题|当前段落主题|封面图绑定整条内容的总标题)\s*[:：]", s):
        return re.split(r"[:：]", s, maxsplit=1)[1].strip()
    return s


def _select_fallback_hook_source(pieces: list[str]) -> str:
    lines = [line.strip() for piece in pieces for line in piece.splitlines() if line.strip()]
    if not lines:
        return ""
    first = lines[0]
    if len(re.sub(r"\s+", "", first)) > 24:
        for candidate in lines[1:]:
            if candidate and candidate != first:
                return candidate
    return first


def _compress_hook_source(text: str, max_chars: int) -> str:
    source = re.sub(r"\s+", " ", text).strip()
    if not source or len(source) <= max_chars:
        return source

    candidates: list[str] = []
    if "是" in source:
        suffix = source.split("是", 1)[1].strip()
        if suffix:
            candidates.append(suffix)
    for sep in ("：", "，", "。"):
        if sep in source:
            suffix = source.split(sep, 1)[1].strip()
            if suffix:
                candidates.append(suffix)
    for candidate in candidates:
        if len(candidate) <= max_chars:
            return candidate
    return source


def _fallback_script(text: str, target_sec: int, source_label: str = "") -> str:
    lo, hi = _target_char_range(target_sec)
    body = _strip_markdown_noise(text)
    raw_pieces = [p.strip() for p in re.split(r"\n{2,}", body) if p.strip()]
    pieces: list[str] = []
    for piece in raw_pieces:
        lines = [_normalize_fallback_line(line) for line in piece.splitlines()]
        lines = [line for line in lines if line]
        if lines:
            pieces.append("\n".join(lines))
    lines: list[str] = []
    if pieces:
        hook_source = _compress_hook_source(_select_fallback_hook_source(pieces), max(8, min(42, hi)))
        hook = _spoken_clip(hook_source, 42)
        if hook:
            lines.append(hook.rstrip("。") + "。")

    detail_blocks = [_spoken_clip(p, 54) for p in pieces[1:] if _spoken_clip(p, 54)]
    if detail_blocks:
        lines.append("详细说说：")
        for idx, item in enumerate(detail_blocks[: _preferred_point_count(target_sec)], 1):
            cn = "一二三四五六七八九十"[idx - 1]
            lines.append(f"{cn}. {item}")
            merged = "".join(lines)
            if len(merged) >= lo:
                break
    if len("".join(lines)) > hi:
        clipped: list[str] = []
        total = 0
        for line in lines:
            if total + len(line) > hi:
                remain = max(0, hi - total - 1)
                if remain > 12:
                    clipped.append(line[:remain] + "…")
                break
            clipped.append(line)
            total += len(line)
        lines = clipped
    return "\n".join(lines).strip() + "\n"


def _read_style_rules() -> str:
    if not STYLE_REF.exists():
        return ""
    return _read_text(STYLE_REF)


def _build_prompts(
    content: str,
    target_sec: int,
    min_sec: int,
    max_sec: int,
    source_label: str = "",
) -> tuple[str, str]:
    lo, hi = _target_char_range(target_sec)
    style_rules = _read_style_rules()
    private_rules = _read_private_script_rules()
    private_examples = _read_private_script_examples()
    system_prompt = (
        "你是 Aki 的短视频口播文案助手。"
        "你只输出可直接口播的中文脚本，不解释，不给方案选项。"
    )
    if style_rules:
        system_prompt += "\n\n请遵守以下风格规则：\n" + style_rules
    if private_rules:
        system_prompt += (
            "\n\n以下是用户自己沉淀的私人口播偏好。"
            "它优先级高于公共规则；只要不违背事实，请尽量按它来写：\n\n"
            + private_rules
        )
    if private_examples:
        system_prompt += (
            "\n\n以下是用户自己的私有口播样本。"
            "你要学习它们的句子密度、口语提纲感、爆点排序和收口方式，"
            "但不要机械复刻原句：\n\n"
            + private_examples
        )

    duration_hint = (
        f"目标时长约 {target_sec} 秒（允许范围 {min_sec}-{max_sec} 秒），"
        f"正文建议字符范围 {lo}-{hi}。"
    )
    source_line = f"\n来源标识：{source_label}" if source_label else ""

    user_prompt = (
        "请把以下内容改写成一版口播脚本：\n"
        f"{duration_hint}{source_line}\n\n"
        "硬性要求：\n"
        "1) 第一行直接给出爆点判断（前3-5秒就说明为什么值得看），不要写“先说结论”“先讲重点”“今天聊聊”这类口头垫词。\n"
        "2) 结构不要固定三点。默认优先拆成 2-4 个展开点；如果题目简单，可以只展开 1-2 点。\n"
        "3) 允许“详细说说：”“一. 二. 三.” 这种口语提纲感，但整体必须仍然是可直接念的成稿，不是文章摘要，也不是会议提纲。\n"
        "4) 短句推进，每行一个信息点，避免长段废话。专业词优先翻成人话。\n"
        "5) 要更像人在对镜头讲，不要把原文标题、小标题、列表原样搬过来。\n"
        "6) 禁止模板腔、禁用空泛 CTA。\n"
        "7) 只输出纯口播正文多行，不要标题，不要时长提示，不要任何说明性前缀。\n"
        "8) 不要 markdown 痕迹，不要 `#`、`##`、`---`、列表符号、编号符号。\n\n"
        "待改写内容如下：\n\n"
        f"{content}\n"
    )
    return system_prompt, user_prompt


def _post_process_script(script: str, target_sec: int) -> str:
    text = script.strip()
    # Drop accidental fenced blocks.
    text = re.sub(r"```[\s\S]*?```", "", text).strip()
    lines = [ln.rstrip() for ln in text.splitlines()]
    # Keep readable breathing room.
    compact: list[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank:
                compact.append("")
            blank = True
            continue
        compact.append(line)
        blank = False
    cleaned: list[str] = []
    for idx, line in enumerate(compact):
        s = line.strip()
        if not s:
            cleaned.append("")
            continue
        if re.match(r"^(来源|平台说明|来源标识|当前段落类型|当前段落主题|全局标题)\s*[:：]", s):
            continue
        if re.match(r"^#\s*视频口播脚本", s):
            continue
        if re.match(r"^视频口播脚本（?约?\d+秒）?$", s):
            continue
        if re.match(r"^-{3,}$", s):
            continue
        s = re.sub(r"^#{1,6}\s*", "", s)
        s = re.sub(r"^[-*•]\s*", "", s)
        s = re.sub(r"^\d+[\.、]\s*", "", s)
        if idx == 0:
            s = re.sub(r"^先说结论[:：]\s*", "", s)
            s = re.sub(r"^先讲重点[:：]\s*", "", s)
            s = re.sub(r"^详细说说[:：]\s*", "", s)
        if s in {"详细说说：", "详细说说"}:
            continue
        if not s.strip():
            continue
        cleaned.append(s)

    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    out = "\n".join(cleaned).strip() + "\n"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Aki-style adaptive Chinese voice script (15s-5min)."
    )
    parser.add_argument("--input", required=True, help="Input markdown/text file")
    parser.add_argument("--output", required=True, help="Output markdown file")
    parser.add_argument("--min-sec", type=int, default=15)
    parser.add_argument("--max-sec", type=int, default=300)
    parser.add_argument("--target-sec", type=int, default=0, help="Optional fixed target seconds")
    parser.add_argument("--model", default="")
    parser.add_argument("--source-label", default="")
    args = parser.parse_args()

    in_path = Path(args.input).expanduser().resolve()
    out_path = Path(args.output).expanduser().resolve()
    if not in_path.exists():
        raise FileNotFoundError(f"Input file not found: {in_path}")
    if args.min_sec <= 0 or args.max_sec <= 0 or args.min_sec > args.max_sec:
        raise ValueError("Invalid min/max seconds")

    source = _read_text(in_path)
    if not source:
        raise RuntimeError("Input content is empty")

    if args.target_sec > 0:
        target_sec = max(args.min_sec, min(args.max_sec, args.target_sec))
    else:
        target_sec = _estimate_target_seconds(source, args.min_sec, args.max_sec)

    system_prompt, user_prompt = _build_prompts(
        content=source,
        target_sec=target_sec,
        min_sec=args.min_sec,
        max_sec=args.max_sec,
        source_label=args.source_label.strip(),
    )

    final_text = ""
    model_override = args.model.strip()
    attempts = [model_override] if model_override else [""]
    if FALLBACK_MODEL not in attempts:
        attempts.append(FALLBACK_MODEL)

    for item in attempts:
        try:
            raw = chat_complete(system_prompt, user_prompt, model_override=item)
            processed = _post_process_script(raw, target_sec)
            if processed.strip():
                final_text = processed
                break
        except Exception:
            continue

    if not final_text:
        final_text = _post_process_script(
            _fallback_script(source, target_sec, args.source_label.strip()),
            target_sec,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(final_text, encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
