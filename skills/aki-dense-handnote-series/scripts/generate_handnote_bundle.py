#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from generate_handnote_series import (
    ensure_parent,
    extract_title,
    generate_image_with_comfly,
    load_image_api_settings,
    read_text,
    strip_frontmatter,
)

COVER_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "aki-handnote-cover" / "scripts"
if str(COVER_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(COVER_SCRIPT_DIR))

from cover_prompt_builder import build_handnote_cover_prompt


STYLE_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "aki-style-library"
    / "references"
    / "styles"
    / "手绘逻辑信息艺术设计师.md"
)
SERIES_CONSTRAINTS_PATH = Path(__file__).resolve().parents[1] / "references" / "constraints.md"
COMFLY_CONFIG = Path.home() / ".config" / "comfly" / "config"
KEYS_ENV = Path("/Users/aki/.config/ai/keys.env")
DEFAULT_CHAT_MODEL = "gemini-3-pro-preview-thinking"

H2_RE = re.compile(r"^##+\s+(.+)$")
SENTENCE_SPLIT_RE = re.compile(r"(?:(?<=[\u3002\uff01\uff1f！？!?])\s*|(?<=\.)\s+)")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|(?:\d+[.)]))\s+")
DECIMAL_DOT_RE = re.compile(r"(?<=\d)\.(?=\d)")
HEADING_PREFIX_RE = re.compile(
    r"^\s*(?:(?:[（(]?\s*(?:[一二三四五六七八九十百千万两\d]+)[.)、．]\s*)|(?:第[一二三四五六七八九十百千万两\d]+(?:部分|章|节)\s*[：:、.]?\s*))"
)

ROLE_ORDER = ["hook", "context", "mechanism", "evidence", "risk", "judgment", "cta"]
ROLE_LABELS = {
    "hook": "爆点",
    "context": "背景",
    "mechanism": "机制",
    "evidence": "证据",
    "risk": "风险",
    "judgment": "判断",
    "cta": "行动号召",
}
ROLE_TITLE = {
    "hook": "爆点与冲击",
    "context": "背景与意义",
    "mechanism": "机制与路径",
    "evidence": "数据与案例",
    "risk": "风险与代价",
    "judgment": "判断与结论",
    "cta": "结尾与行动",
}

ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "hook": (
        "先说结论",
        "爆点",
        "刚刚",
        "第一",
        "登顶",
        "破纪录",
        "历史神话",
        "从零到第一",
        "只用了",
        "为什么这么狂",
    ),
    "context": (
        "GitHub",
        "星标",
        "为什么重要",
        "意味着什么",
        "背景",
        "过去十年",
        "长期",
    ),
    "mechanism": (
        "本地",
        "Agent",
        "智能体",
        "调用工具",
        "执行",
        "流程",
        "自动化",
        "跨体系",
    ),
    "evidence": (
        "数据",
        "案例",
        "比如",
        "例如",
        "25万",
        "243K",
        "220K",
        "100天",
        "三个月",
    ),
    "risk": (
        "风险",
        "成本",
        "安全",
        "稳定性",
        "裸奔",
        "权限",
        "审计",
        "暴露公网",
    ),
    "judgment": (
        "我的判断",
        "结论",
        "本质",
        "说明",
        "底层逻辑",
        "行业洗牌",
        "时代变了",
    ),
    "cta": (
        "你怎么看",
        "评论区",
        "欢迎留言",
        "你准备好",
        "说说你的看法",
    ),
}


@dataclass
class LogicUnit:
    id: int
    heading: str
    text: str
    role: str

    @property
    def chars(self) -> int:
        return len(self.text)


@dataclass
class PageSpec:
    title: str
    kind: str  # content | ending
    units: list[LogicUnit]

    @property
    def roles(self) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for unit in self.units:
            if unit.role in seen:
                continue
            out.append(unit.role)
            seen.add(unit.role)
        return out


def _parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        key = k.strip()
        value = v.strip().strip('"').strip("'")
        if key:
            data[key] = value
    return data


def _normalize_chat_url(raw: str) -> str:
    value = raw.strip()
    if not value:
        value = "https://ai.comfly.chat"
    if value.endswith("/v1/chat/completions"):
        return value
    return value.rstrip("/") + "/v1/chat/completions"


def _chat_complete(system_prompt: str, user_prompt: str, model_override: str = "") -> str:
    file_cfg = _parse_env_file(COMFLY_CONFIG)
    keys_cfg = _parse_env_file(KEYS_ENV)
    api_key = (
        os.getenv("COMFLY_API_KEY")
        or keys_cfg.get("COMFLY_API_KEY")
        or file_cfg.get("COMFLY_API_KEY")
        or file_cfg.get("API_KEY")
        or ""
    ).strip()
    if not api_key:
        raise RuntimeError(f"Missing COMFLY_API_KEY (set env or {COMFLY_CONFIG})")

    raw_url = (
        os.getenv("COMFLY_API_URL")
        or keys_cfg.get("COMFLY_API_URL")
        or file_cfg.get("COMFLY_API_URL")
        or os.getenv("COMFLY_API_BASE_URL")
        or keys_cfg.get("COMFLY_API_BASE_URL")
        or file_cfg.get("COMFLY_API_BASE_URL")
        or ""
    ).strip()
    api_url = _normalize_chat_url(raw_url)

    model = (
        model_override.strip()
        or os.getenv("COMFLY_CHAT_MODEL")
        or keys_cfg.get("COMFLY_CHAT_MODEL")
        or os.getenv("COMFLY_MODEL")
        or keys_cfg.get("COMFLY_MODEL")
        or file_cfg.get("COMFLY_CHAT_MODEL")
        or file_cfg.get("COMFLY_MODEL")
        or DEFAULT_CHAT_MODEL
    ).strip()

    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    req = Request(
        url=api_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "aki-dense-handnote-series/logic-bundle",
        },
    )
    with urlopen(req, timeout=180) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Empty LLM response: {raw[:400]}")
    content = (((choices[0] or {}).get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("LLM response content is empty")
    return content


def _normalize_for_compare(text: str) -> str:
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE).lower()


def _clean_heading_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    cleaned = HEADING_PREFIX_RE.sub("", raw).strip()
    return cleaned or raw


def _split_sentences(text: str) -> list[str]:
    protected = DECIMAL_DOT_RE.sub("__AKI_DECIMAL_DOT__", text)
    parts = [s.strip() for s in SENTENCE_SPLIT_RE.split(protected) if s.strip()]
    return [part.replace("__AKI_DECIMAL_DOT__", ".") for part in parts]


def _first_sentence(text: str, max_chars: int = 28) -> str:
    parts = _split_sentences(text)
    if not parts:
        return text[:max_chars].strip()
    head = parts[0]
    if re.fullmatch(r"\d+[.)]?", head) and len(parts) > 1:
        head = parts[1]
    if len(head) <= max_chars:
        return head
    return head[:max_chars].rstrip("，,。.;；:：!?！？") + "…"


def _split_to_units(article_text: str) -> list[LogicUnit]:
    lines = article_text.splitlines()
    units_raw: list[tuple[str, str]] = []
    heading = ""
    buf: list[str] = []
    in_list = False

    def flush() -> None:
        if not buf:
            return
        block = "\n".join(buf).strip()
        buf.clear()
        if not block:
            return
        if block.startswith("# "):
            return
        units_raw.append((heading, block))

    for raw in lines:
        line = raw.strip()
        if not line:
            in_list = False
            flush()
            continue
        if line.startswith("# "):
            in_list = False
            flush()
            continue
        hm = H2_RE.match(line)
        if hm:
            in_list = False
            flush()
            heading = hm.group(1).strip()
            continue
        is_list_item = bool(LIST_ITEM_RE.match(line))
        if is_list_item and buf and not in_list:
            flush()
        elif (not is_list_item) and in_list and buf:
            flush()
        buf.append(line)
        in_list = is_list_item
    flush()

    if not units_raw:
        text = article_text.strip()
        if text:
            units_raw = [("", text)]

    units: list[LogicUnit] = []
    for idx, (h, text) in enumerate(units_raw, start=1):
        units.append(LogicUnit(id=idx, heading=h, text=text.strip(), role="mechanism"))
    return units


def _detect_role(text: str, heading: str, idx: int, total: int) -> str:
    haystack = f"{heading}\n{text}".lower()
    scores: dict[str, int] = {role: 0 for role in ROLE_ORDER}
    for role, keywords in ROLE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in haystack:
                scores[role] += 2 if keyword.lower() in heading.lower() else 1

    if idx == 0:
        scores["hook"] += 3
    if idx >= total - 1:
        scores["judgment"] += 2
    if idx >= total - 2:
        scores["cta"] += 1
    if "?" in text or "？" in text:
        scores["cta"] += 1

    best_role = max(scores.items(), key=lambda kv: kv[1])[0]
    if scores[best_role] <= 0:
        if idx == 0:
            return "hook"
        if idx >= total - 1:
            return "judgment"
        return "mechanism"
    return best_role


def _assign_roles(units: list[LogicUnit]) -> list[LogicUnit]:
    total = len(units)
    for idx, unit in enumerate(units):
        unit.role = _detect_role(unit.text, unit.heading, idx, total)
    return units


def _merge_short_units(units: list[LogicUnit], min_chars: int = 80) -> list[LogicUnit]:
    if not units:
        return units
    merged: list[LogicUnit] = []
    for unit in units:
        can_merge = (
            bool(merged)
            and unit.chars < min_chars
            and unit.role == merged[-1].role
            and (not unit.heading or unit.heading == merged[-1].heading)
        )
        if can_merge:
            prev = merged[-1]
            prev.text = (prev.text + "\n\n" + unit.text).strip()
            if not prev.heading and unit.heading:
                prev.heading = unit.heading
            continue
        merged.append(unit)
    for idx, unit in enumerate(merged, start=1):
        unit.id = idx
    return merged


def _merge_heading_runs(units: list[LogicUnit]) -> list[LogicUnit]:
    if not units:
        return units
    merged: list[LogicUnit] = []
    for unit in units:
        cleaned_heading = _clean_heading_text(unit.heading)
        if (
            merged
            and cleaned_heading
            and cleaned_heading == _clean_heading_text(merged[-1].heading)
        ):
            prev = merged[-1]
            prev.text = (prev.text + "\n\n" + unit.text).strip()
            prev.role = prev.role or unit.role
            continue
        merged.append(unit)
    for idx, unit in enumerate(merged, start=1):
        unit.id = idx
    return merged


def _dedupe_units(units: list[LogicUnit]) -> list[LogicUnit]:
    seen: set[str] = set()
    out: list[LogicUnit] = []
    for unit in units:
        key = _normalize_for_compare(unit.text)
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(unit)
    for idx, unit in enumerate(out, start=1):
        unit.id = idx
    return out


def _split_unit_by_sentence(unit: LogicUnit) -> list[LogicUnit]:
    sentences = _split_sentences(unit.text)
    if len(sentences) < 2:
        return [unit]
    total_chars = sum(len(s) for s in sentences)
    target = total_chars // 2
    left: list[str] = []
    right: list[str] = []
    cur = 0
    for idx, sentence in enumerate(sentences):
        if cur < target or idx == 0:
            left.append(sentence)
            cur += len(sentence)
        else:
            right.append(sentence)
    if not right:
        return [unit]
    right_heading = unit.heading if not unit.heading else ""
    return [
        LogicUnit(id=0, heading=unit.heading, text="".join(left).strip(), role=unit.role),
        LogicUnit(id=0, heading=right_heading, text="".join(right).strip(), role=unit.role),
    ]


def _split_unit_force(unit: LogicUnit) -> list[LogicUnit]:
    split = _split_unit_by_sentence(unit)
    if len(split) == 2:
        return split
    text = unit.text.strip()
    if len(text) < 2:
        return [unit]
    pivot = len(text) // 2
    punctuation = "。！？.!?；;：:,，、"
    for offset in range(0, 18):
        right = pivot + offset
        left = pivot - offset
        if right < len(text) - 1 and text[right] in punctuation:
            pivot = right + 1
            break
        if left > 0 and text[left] in punctuation:
            pivot = left + 1
            break
    left_text = text[:pivot].strip()
    right_text = text[pivot:].strip()
    if not left_text or not right_text:
        pivot = max(1, min(len(text) - 1, len(text) // 2))
        left_text = text[:pivot].strip()
        right_text = text[pivot:].strip()
    if not left_text or not right_text:
        return [unit]
    right_heading = unit.heading if not unit.heading else ""
    return [
        LogicUnit(id=0, heading=unit.heading, text=left_text, role=unit.role),
        LogicUnit(id=0, heading=right_heading, text=right_text, role=unit.role),
    ]


def _ensure_min_unit_count(units: list[LogicUnit], target: int) -> list[LogicUnit]:
    out = list(units)
    if not out:
        return out
    while len(out) < target:
        longest_idx = max(range(len(out)), key=lambda i: out[i].chars)
        split = _split_unit_force(out[longest_idx])
        if len(split) == 1:
            break
        out = out[:longest_idx] + split + out[longest_idx + 1 :]
    for idx, unit in enumerate(out, start=1):
        unit.id = idx
    return out


def _complexity_score(units: list[LogicUnit]) -> int:
    roles = {unit.role for unit in units if unit.role != "cta"}
    headings = {unit.heading for unit in units if unit.heading}
    list_items = sum(len(re.findall(r"(?m)^\s*(?:[-*]|\d+\.)\s+", unit.text)) for unit in units)
    numeric_signals = sum(len(re.findall(r"\d+[%万千Kk]?", unit.text)) for unit in units)
    score = 0
    score += len(roles) * 2
    score += min(len(headings), 5)
    score += min(list_items // 2, 4)
    score += min(numeric_signals // 3, 3)
    return score


def _target_content_pages(units: list[LogicUnit], min_pages: int, max_pages: int) -> int:
    score = _complexity_score(units)
    total_chars = sum(unit.chars for unit in units)
    soft_cap = max_pages
    if total_chars <= 650:
        soft_cap = min(3, max_pages)
    elif total_chars <= 1100:
        soft_cap = min(4, max_pages)
    elif total_chars <= 1700:
        soft_cap = min(5, max_pages)
    if score <= 6:
        target = min_pages
    elif score <= 10:
        target = min(max_pages, min_pages + 1)
    else:
        target = max_pages
    target = min(target, soft_cap)
    return max(min_pages, min(max_pages, target))


def _group_units_rule(units: list[LogicUnit], page_count: int) -> list[list[LogicUnit]]:
    if page_count <= 1:
        return [units]
    total_chars = max(1, sum(unit.chars for unit in units))
    target_chars = max(220, total_chars // page_count)
    groups: list[list[LogicUnit]] = []
    current: list[LogicUnit] = []
    current_chars = 0

    for i, unit in enumerate(units):
        remaining_units = len(units) - i
        remaining_pages = page_count - len(groups)
        must_break = bool(current) and remaining_units == remaining_pages
        role_boundary = (
            bool(current)
            and unit.role != current[-1].role
            and current_chars >= int(target_chars * 0.75)
            and len(groups) < page_count - 1
        )
        over_target = bool(current) and current_chars >= target_chars and len(groups) < page_count - 1
        if must_break or role_boundary or over_target:
            groups.append(current)
            current = []
            current_chars = 0
        current.append(unit)
        current_chars += unit.chars
    if current:
        groups.append(current)

    while len(groups) > page_count:
        merge_idx = min(
            range(len(groups) - 1),
            key=lambda idx: sum(u.chars for u in groups[idx]) + sum(u.chars for u in groups[idx + 1]),
        )
        groups[merge_idx] = groups[merge_idx] + groups[merge_idx + 1]
        del groups[merge_idx + 1]

    while len(groups) < page_count:
        split_idx = max(range(len(groups)), key=lambda idx: sum(u.chars for u in groups[idx]))
        candidate = groups[split_idx]
        if len(candidate) >= 2:
            pivot = len(candidate) // 2
            left, right = candidate[:pivot], candidate[pivot:]
        else:
            split = _split_unit_force(candidate[0])
            if len(split) == 1:
                break
            left, right = [split[0]], [split[1]]
        groups[split_idx] = left
        groups.insert(split_idx + 1, right)
    return groups


def _dominant_role(units: list[LogicUnit]) -> str:
    if not units:
        return "mechanism"
    score: dict[str, int] = {}
    for unit in units:
        score[unit.role] = score.get(unit.role, 0) + unit.chars
    return max(score.items(), key=lambda kv: kv[1])[0]


def _layout_guidance_for_page(page: PageSpec) -> str:
    dominant = _dominant_role(page.units)
    roles = set(page.roles)
    base = (
        "布局让内容自己决定，不要为了形式硬凑左中右分区、123 步骤或机械对比版式。"
    )
    role_guidance = {
        "hook": "适合用一个核心判断带 2-4 个支撑点，强调冲击和后果，不要只剩一个大标题。",
        "context": "适合用背景脉络、问题-意义或时间线组织，让读者先理解这件事为什么重要。",
        "mechanism": "优先因果链、流程链或层级递进，讲清楚这件事怎么发生、怎么运转、代价在哪。",
        "evidence": "优先证据卡片、案例并列或数据分组，让事实支撑判断，而不是堆装饰。",
        "risk": "优先代价/限制/门槛分组，把风险点展开，不要只做危言耸听的大字。",
        "judgment": "优先结论 + 支撑理由，让判断和依据连在一起，不要写成空泛总结页。",
        "cta": "优先收口与行动建议，可用简短提醒，但仍要带信息，不要只剩口号。",
    }
    extra: list[str] = []
    if {"mechanism", "risk"} <= roles:
        extra.append("当前页同时有机制和代价，允许主链旁加限制/成本侧注。")
    if {"evidence", "judgment"} <= roles:
        extra.append("当前页同时有证据和判断，适合先摆事实，再收束到结论。")
    if {"context", "hook"} <= roles:
        extra.append("当前页同时有背景和爆点，适合先给冲击，再补“为什么值得看”。")
    lines = [
        "Series Layout Guidance:",
        f"- 当前主导角色：{ROLE_LABELS.get(dominant, dominant)}",
        f"- {role_guidance.get(dominant, base)}",
        f"- {base}",
    ]
    lines.extend(f"- {item}" for item in extra)
    return "\n".join(lines)


def _dominant_heading(units: list[LogicUnit]) -> str:
    scores: dict[str, int] = {}
    labels: dict[str, str] = {}
    for unit in units:
        heading = _clean_heading_text(unit.heading)
        if not heading:
            continue
        key = _normalize_for_compare(heading)
        if not key:
            continue
        scores[key] = scores.get(key, 0) + unit.chars
        labels[key] = heading
    if not scores:
        return ""
    best_key = max(scores.items(), key=lambda item: item[1])[0]
    return labels.get(best_key, "")


def _fallback_title_from_units(units: list[LogicUnit], idx: int, total: int) -> str:
    role = _dominant_role(units)
    base = ROLE_TITLE.get(role, f"内容 {idx + 1}")
    source_unit = max(units, key=lambda unit: unit.chars) if units else None
    sentence = _first_sentence(source_unit.text if source_unit else "", 20)
    if sentence:
        return f"{base}：{sentence}"
    return f"{base}（{idx + 1}/{total}）"


def _derive_page_title(units: list[LogicUnit], idx: int, total: int, cover_title: str) -> str:
    heading = _dominant_heading(units)
    if heading and _normalize_for_compare(heading) != _normalize_for_compare(cover_title):
        return heading
    title = _fallback_title_from_units(units, idx, total)
    if _normalize_for_compare(title) != _normalize_for_compare(cover_title):
        return title
    return f"{title}（{idx + 1}）"


def _ensure_unique_page_titles(pages: list[PageSpec], cover_title: str) -> list[PageSpec]:
    seen: set[str] = set()
    total = len(pages)
    for idx, page in enumerate(pages):
        base_title = _clean_heading_text(page.title)
        if not base_title:
            base_title = _derive_page_title(page.units, idx, total, cover_title)
        candidate = base_title
        candidate_key = _normalize_for_compare(candidate)
        if not candidate_key or candidate_key in seen:
            candidate = _fallback_title_from_units(page.units, idx, total)
            candidate_key = _normalize_for_compare(candidate)
        suffix = 2
        while not candidate_key or candidate_key in seen:
            candidate = f"{_fallback_title_from_units(page.units, idx, total)}（{suffix}）"
            candidate_key = _normalize_for_compare(candidate)
            suffix += 1
        page.title = candidate
        seen.add(candidate_key)
    return pages


def _has_role_imbalance(groups: list[list[LogicUnit]]) -> bool:
    risk_pages = sum(1 for group in groups if any(unit.role == "risk" for unit in group))
    risk_units = sum(1 for group in groups for unit in group if unit.role == "risk")
    if risk_units >= 2 and len(groups) >= 3 and risk_pages <= 1:
        return True
    return False


def _has_thin_pages(groups: list[list[LogicUnit]], min_chars: int = 110) -> bool:
    if len(groups) <= 1:
        return False
    for group in groups:
        total_chars = sum(unit.chars for unit in group)
        if total_chars < min_chars:
            return True
    return False


def _extract_json_payload(text: str) -> dict[str, Any]:
    raw = text.strip()
    if not raw:
        raise RuntimeError("LLM fallback returned empty content")
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n", "", raw)
        raw = re.sub(r"\n```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError("LLM fallback did not return JSON object")
    return json.loads(raw[start : end + 1])


def _plan_pages_with_llm(
    units: list[LogicUnit],
    min_pages: int,
    max_pages: int,
    cover_title: str,
    model_override: str = "",
) -> tuple[list[list[LogicUnit]], list[str]] | None:
    unit_payload = []
    for unit in units:
        unit_payload.append(
            {
                "id": unit.id,
                "heading": unit.heading,
                "role": unit.role,
                "chars": unit.chars,
                "text_preview": _first_sentence(unit.text, 80),
            }
        )

    system_prompt = (
        "你是内容结构编辑。你的任务是按语义和信息密度，把一篇文章规划成多张内容页。"
        "必须避免机械分页、避免空心页、避免把同一标题下的引子和正文拆开。只输出 JSON。"
    )
    user_prompt = (
        "请根据以下逻辑单元输出页面规划。\n"
        f"全局标题：{cover_title}\n"
        f"约束：content_pages 在 [{min_pages}, {max_pages}]；每个单元只能出现一次；不得遗漏。\n"
        "分页原则：\n"
        "1) 由你动态决定页数，不要为了凑满上限硬拆内容；\n"
        "2) 短稿宁可 3-4 页，也不要拆成很多薄页；\n"
        "3) 同一小标题下的引子、表格、结论尽量放在同一页；\n"
        "4) 不要让单独一句过渡句、单独一个表格说明、单独一个收口句成为一页；\n"
        "5) 每一页都要有明确主题和足够信息量；\n"
        "6) page theme 要像正常人写的分页标题，不要写“机制与路径”“判断与结论”这种空标题，除非没有更具体的主题。\n"
        "输出 JSON 结构：\n"
        "{\n"
        '  "pages": [\n'
        '    {"theme": "页面主题", "unit_ids": [1,2]}\n'
        "  ]\n"
        "}\n\n"
        f"逻辑单元：\n{json.dumps(unit_payload, ensure_ascii=False, indent=2)}"
    )
    try:
        content = _chat_complete(system_prompt, user_prompt, model_override=model_override)
        payload = _extract_json_payload(content)
    except Exception:
        return None

    pages = payload.get("pages")
    if not isinstance(pages, list):
        return None
    if not (min_pages <= len(pages) <= max_pages):
        return None

    by_id = {unit.id: unit for unit in units}
    seen: set[int] = set()
    groups: list[list[LogicUnit]] = []
    titles: list[str] = []
    for page in pages:
        if not isinstance(page, dict):
            return None
        theme = str(page.get("theme") or "").strip()
        ids = page.get("unit_ids")
        if not isinstance(ids, list) or not ids:
            return None
        group: list[LogicUnit] = []
        for raw_id in ids:
            if not isinstance(raw_id, int):
                return None
            if raw_id not in by_id:
                return None
            if raw_id in seen:
                return None
            seen.add(raw_id)
            group.append(by_id[raw_id])
        groups.append(group)
        titles.append(theme or "")
    if seen != set(by_id):
        return None
    return groups, titles


def _detect_ending_units(units: list[LogicUnit], policy: str) -> list[LogicUnit]:
    if policy == "never":
        return []
    if policy == "always":
        tail = units[-2:] if len(units) >= 2 else units[-1:]
        return list(tail)
    # adaptive
    candidates = [unit for unit in units[-3:] if unit.role == "cta"]
    if candidates:
        return candidates
    tail_text = "\n".join(unit.text for unit in units[-2:])
    cta_hit = any(keyword in tail_text for keyword in ROLE_KEYWORDS["cta"])
    if cta_hit:
        return units[-2:]
    return []


def _plan_pages(
    units: list[LogicUnit],
    min_pages: int,
    max_pages: int,
    logic_mode: str,
    cover_title: str,
    ending_policy: str,
    model_override: str = "",
) -> tuple[list[PageSpec], bool]:
    ending_units = _detect_ending_units(units, ending_policy)
    ending_ids = {unit.id for unit in ending_units}
    content_units = [unit for unit in units if unit.id not in ending_ids]
    if not content_units:
        content_units = units
        ending_units = []
        ending_ids = set()

    target = _target_content_pages(content_units, min_pages, max_pages)
    content_units = _ensure_min_unit_count(content_units, target)

    groups = _group_units_rule(content_units, target)
    title_overrides: list[str] = ["" for _ in groups]
    need_llm = (
        logic_mode in {"hybrid", "llm"}
        or len(groups) != target
        or any(not group for group in groups)
        or _has_role_imbalance(groups)
        or _has_thin_pages(groups)
    )

    fallback_used = False
    if need_llm:
        llm_plan = _plan_pages_with_llm(
            content_units,
            min_pages,
            max_pages,
            cover_title=cover_title,
            model_override=model_override,
        )
        if llm_plan is not None:
            groups, title_overrides = llm_plan
            fallback_used = True
        elif logic_mode == "llm":
            raise RuntimeError("LLM logic planning failed in logic-mode=llm")

    if len(groups) < min_pages:
        groups = _group_units_rule(content_units, min_pages)
    if _has_thin_pages(groups):
        thinner_target = max(min_pages, min(len(groups) - 1, target - 1))
        if thinner_target < len(groups):
            groups = _group_units_rule(content_units, thinner_target)
            title_overrides = ["" for _ in groups]

    page_specs: list[PageSpec] = []
    for idx, group in enumerate(groups):
        title = title_overrides[idx] if idx < len(title_overrides) else ""
        title = title.strip()
        if not title:
            title = _derive_page_title(group, idx, len(groups), cover_title)
        if _normalize_for_compare(title) == _normalize_for_compare(cover_title):
            title = _derive_page_title(group, idx, len(groups), cover_title + " ")
        page_specs.append(PageSpec(title=title, kind="content", units=group))

    if ending_units:
        ending_title = "结尾：你怎么看"
        page_specs.append(PageSpec(title=ending_title, kind="ending", units=ending_units))

    return _ensure_unique_page_titles(page_specs, cover_title), fallback_used


def _load_required_text(path: Path, label: str) -> str:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    return read_text(path)


def _build_cover_prompt(
    title: str,
    article_text: str,
) -> str:
    return build_handnote_cover_prompt(article_text, title)


def _build_series_prompt(
    article_title: str,
    page_idx: int,
    total_pages: int,
    page: PageSpec,
    series_constraints: str,
    style_text: str,
    metadata_level: str,
) -> str:
    source_blocks: list[str] = []
    for unit in page.units:
        cleaned_heading = _clean_heading_text(unit.heading)
        if cleaned_heading:
            source_blocks.append(f"### {cleaned_heading}\n{unit.text.strip()}")
        else:
            source_blocks.append(unit.text.strip())
    source_text = "\n\n".join(source_blocks).strip()
    dominant = _dominant_role(page.units)
    page_type = "Ending" if page.kind == "ending" else "Content"

    if metadata_level == "minimal":
        parts = [
            series_constraints.strip(),
            style_text.strip(),
            "Series Page Note:\n"
            "- 这是正文内容页，不是封面页。\n"
            "- 页面主题只取当前页内容，不要把整篇文章标题做成页面顶部超大字。\n"
            "- 布局形式服从原文逻辑，可分组、递进、对比，但不要为了形式硬凑模板。\n"
            "- 画布背景必须保持纯白底，不要米白纸张感、灰底或笔记本纹理。\n"
            "- 以 2K 级画布为基准，四周至少保留 48px 安全留白，所有标题、正文、箭头、图标、标注都不能贴边。",
            f"Page Type: {page_type}",
            f"Page Theme: {page.title}",
            "Source Material:\n" + source_text,
        ]
    else:
        hard_constraints = (
            "Series Page Intent:\n"
            "- 这是正文内容页，不是封面页。\n"
            "- 页面主题应来自当前页内容，不要把整篇文章标题做成页面顶部超大字。\n"
            "- 控制字段只用于理解当前页位置与角色，不要把字段标签直接渲染到画面上。\n"
            "- 保持清晰的信息层级和多个信息节点，但布局形式必须服从内容逻辑。\n"
            "- 背景必须是纯白底，不要米白、灰底、纸张纹理或笔记本装订视觉。\n"
            "- 以 2K 级画布为基准，四周至少保留 48px 安全留白，所有标题、正文、箭头、图标、标注都必须留在安全区内。"
        )
        metadata_block = (
            "Layout Control Metadata (for planning only, do not render these labels as on-page text):\n"
            f"- Whole Article Title: {article_title}\n"
            f"- Current Page: {page_idx}/{total_pages}\n"
            f"- Page Kind: {page_type}\n"
            f"- Current Theme Anchor: {page.title}\n"
            f"- Dominant Role: {ROLE_LABELS.get(dominant, dominant)}"
        )
        kind_tip = (
            "Page Kind: Ending (summary/CTA page)"
            if page.kind == "ending"
            else "Page Kind: Content"
        )
        parts = [
            series_constraints.strip(),
            style_text.strip(),
            hard_constraints,
            metadata_block,
            _layout_guidance_for_page(page),
            kind_tip,
            f"Page Theme (use as this page's content anchor, not raw label): {page.title}",
            f"Primary Role (guide layout, not display text): {ROLE_LABELS.get(dominant, dominant)}",
            "Source Material:\n" + source_text,
        ]
    return "\n\n".join(parts).strip() + "\n"


def _clear_series_prompt_files(prompts_output_dir: Path, series_prompt_dir: Path) -> None:
    for path in prompts_output_dir.glob("series_*_prompt.md"):
        if path.is_file():
            path.unlink()
    if series_prompt_dir.exists():
        for path in series_prompt_dir.glob("*.md"):
            if path.is_file():
                path.unlink()


def _remove_dir_if_empty(path: Path) -> None:
    if not path.exists() or not path.is_dir():
        return
    try:
        next(path.iterdir())
    except StopIteration:
        path.rmdir()


def _write_outline(
    path: Path,
    title: str,
    logic_mode: str,
    fallback_used: bool,
    content_min: int,
    content_max: int,
    pages: list[PageSpec],
) -> None:
    lines = [
        "# Handnote Bundle Outline",
        "",
        f"Title: {title}",
        f"Logic Mode: {logic_mode}",
        f"LLM Fallback Used: {str(fallback_used).lower()}",
        f"Content Page Range: {content_min}-{content_max}",
        f"Pages (without cover): {len(pages)}",
        "",
    ]
    for idx, page in enumerate(pages, start=1):
        lines.append(f"## Page {idx:02d}")
        lines.append(f"- Kind: {page.kind}")
        lines.append(f"- Theme: {page.title}")
        roles = ", ".join(ROLE_LABELS.get(role, role) for role in page.roles)
        lines.append(f"- Roles: {roles or '(none)'}")
        lines.append(f"- Units: {', '.join(str(unit.id) for unit in page.units)}")
        preview = _first_sentence(" ".join(unit.text for unit in page.units), 120)
        lines.append(f"- Preview: {preview}")
        lines.append("")
    ensure_parent(path)
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _build_bundle(
    article_text: str,
    article_title: str,
    outline_output: Path,
    content_min_pages: int,
    content_max_pages: int,
    ending_policy: str,
    logic_mode: str,
    llm_model: str,
    include_cover: bool,
    metadata_level: str,
) -> tuple[str | None, list[str], list[PageSpec], bool]:
    units = _assign_roles(_split_to_units(article_text))
    units = _merge_heading_runs(_dedupe_units(_merge_short_units(units)))
    if not units:
        raise RuntimeError("No logic units extracted from article")

    pages, fallback_used = _plan_pages(
        units=units,
        min_pages=content_min_pages,
        max_pages=content_max_pages,
        logic_mode=logic_mode,
        cover_title=article_title,
        ending_policy=ending_policy,
        model_override=llm_model,
    )

    series_constraints = _load_required_text(SERIES_CONSTRAINTS_PATH, "Series constraints")
    style_text = _load_required_text(STYLE_TEMPLATE_PATH, "Style template")

    cover_prompt: str | None = None
    if include_cover:
        cover_prompt = _build_cover_prompt(article_title, article_text)

    series_prompts: list[str] = []
    total_pages = len(pages)
    for idx, page in enumerate(pages, start=1):
        series_prompts.append(
            _build_series_prompt(
                article_title=article_title,
                page_idx=idx,
                total_pages=total_pages,
                page=page,
                series_constraints=series_constraints,
                style_text=style_text,
                metadata_level=metadata_level,
            )
        )

    _write_outline(
        path=outline_output,
        title=article_title,
        logic_mode=logic_mode,
        fallback_used=fallback_used,
        content_min=content_min_pages,
        content_max=content_max_pages,
        pages=pages,
    )

    return cover_prompt, series_prompts, pages, fallback_used


def _save_prompts(
    cover_prompt: str | None,
    series_prompts: list[str],
    prompts_output_dir: Path,
    series_prompt_dir: Path,
    outline_output: Path,
    mirror_series_prompts: bool,
) -> tuple[Path | None, list[Path]]:
    prompts_output_dir.mkdir(parents=True, exist_ok=True)
    _clear_series_prompt_files(prompts_output_dir, series_prompt_dir)
    ensure_parent(outline_output)
    if mirror_series_prompts:
        series_prompt_dir.mkdir(parents=True, exist_ok=True)
    else:
        legacy_outline = series_prompt_dir.parent / "outline.md"
        if legacy_outline.exists() and legacy_outline != outline_output:
            legacy_outline.unlink()

    cover_prompt_path = prompts_output_dir / "cover_prompt.md"
    if cover_prompt is not None:
        cover_prompt_path.write_text(cover_prompt, encoding="utf-8")
    elif cover_prompt_path.exists():
        cover_prompt_path.unlink()

    series_prompt_paths: list[Path] = []
    width = max(2, len(str(len(series_prompts))))
    for idx, prompt in enumerate(series_prompts, start=1):
        label = str(idx).zfill(width)
        out1 = prompts_output_dir / f"series_{label}_prompt.md"
        out1.write_text(prompt, encoding="utf-8")
        if mirror_series_prompts:
            out2 = series_prompt_dir / f"{label}.md"
            out2.write_text(prompt, encoding="utf-8")
        series_prompt_paths.append(out1)
    _remove_dir_if_empty(series_prompt_dir)
    return (cover_prompt_path if cover_prompt is not None else None), series_prompt_paths


def _render_images(
    cover_prompt: str | None,
    series_prompts: list[str],
    cover_output: Path,
    series_output_dir: Path,
    skills_root: Path,
    model_override: str,
    render_series_limit: int,
) -> tuple[Path | None, list[Path]]:
    settings = load_image_api_settings(skills_root)
    if model_override:
        print(
            "Warning: --model is ignored; set COMFLY_IMAGE_MODEL in ~/.config/comfly/config.",
            file=sys.stderr,
        )

    generated_cover: Path | None = None
    if cover_prompt is not None:
        ensure_parent(cover_output)
        generate_image_with_comfly(cover_prompt, cover_output, settings)
        generated_cover = cover_output

    series_output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    prompts_to_render = series_prompts
    if render_series_limit > 0:
        prompts_to_render = series_prompts[:render_series_limit]
    width = max(2, len(str(len(series_prompts))))
    for idx, prompt in enumerate(prompts_to_render, start=1):
        label = str(idx).zfill(width)
        output = series_output_dir / f"{label}.png"
        generate_image_with_comfly(prompt, output, settings)
        generated.append(output)
    return generated_cover, generated


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate handnote cover + logic-based series pages in one unified run."
    )
    parser.add_argument("--article", required=True)
    parser.add_argument("--cover-output", required=True)
    parser.add_argument("--series-output-dir", required=True)
    parser.add_argument("--prompts-output-dir", required=True)
    parser.add_argument("--outline-output", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--content-min-pages", type=int, default=2)
    parser.add_argument("--content-max-pages", type=int, default=4)
    parser.add_argument("--ending-policy", choices=["adaptive", "always", "never"], default="adaptive")
    parser.add_argument("--logic-mode", choices=["hybrid", "rule", "llm"], default="hybrid")
    parser.add_argument("--skip-cover", action="store_true")
    parser.add_argument("--prompt-only", action="store_true")
    parser.add_argument("--render", action="store_true", help="Force rendering even when other modes are used.")
    parser.add_argument("--model", default="", help="Legacy option (ignored, use COMFLY_IMAGE_MODEL)")
    parser.add_argument("--llm-model", default="", help="Chat model override for fallback planner")
    parser.add_argument("--prompt-storage", choices=["dual", "single"], default="dual")
    parser.add_argument("--metadata-level", choices=["verbose", "minimal"], default="verbose")
    parser.add_argument(
        "--render-series-limit",
        type=int,
        default=0,
        help="Only render the first N series images (0 renders all generated series prompts).",
    )
    args = parser.parse_args()

    if args.content_min_pages <= 0 or args.content_max_pages <= 0:
        raise ValueError("content page limits must be positive")
    if args.content_min_pages > args.content_max_pages:
        raise ValueError("content-min-pages cannot exceed content-max-pages")

    article_path = Path(args.article).expanduser().resolve()
    if not article_path.exists():
        raise FileNotFoundError(f"Article not found: {article_path}")

    cover_output = Path(args.cover_output).expanduser().resolve()
    series_output_dir = Path(args.series_output_dir).expanduser().resolve()
    prompts_output_dir = Path(args.prompts_output_dir).expanduser().resolve()
    outline_output = Path(args.outline_output).expanduser().resolve()
    series_prompt_dir = series_output_dir / "prompts"

    article_text = strip_frontmatter(read_text(article_path))
    if not article_text.strip():
        raise RuntimeError("Article is empty after preprocessing")
    title = args.title.strip() or extract_title(article_text) or "未命名话题"

    skill_root = Path(__file__).resolve().parents[1]
    skills_root = skill_root.parent

    cover_prompt, series_prompts, pages, fallback_used = _build_bundle(
        article_text=article_text,
        article_title=title,
        outline_output=outline_output,
        content_min_pages=args.content_min_pages,
        content_max_pages=args.content_max_pages,
        ending_policy=args.ending_policy,
        logic_mode=args.logic_mode,
        llm_model=args.llm_model,
        include_cover=not args.skip_cover,
        metadata_level=args.metadata_level,
    )
    cover_prompt_path, series_prompt_paths = _save_prompts(
        cover_prompt=cover_prompt,
        series_prompts=series_prompts,
        prompts_output_dir=prompts_output_dir,
        series_prompt_dir=series_prompt_dir,
        outline_output=outline_output,
        mirror_series_prompts=(args.prompt_storage == "dual"),
    )

    should_render = args.render or not args.prompt_only
    generated_cover: Path | None = None
    generated_series: list[Path] = []
    if should_render:
        generated_cover, generated_series = _render_images(
            cover_prompt=cover_prompt,
            series_prompts=series_prompts,
            cover_output=cover_output,
            series_output_dir=series_output_dir,
            skills_root=skills_root,
            model_override=args.model.strip(),
            render_series_limit=max(0, args.render_series_limit),
        )

    summary = {
        "title": title,
        "logic_mode": args.logic_mode,
        "cover_enabled": not args.skip_cover,
        "fallback_used": fallback_used,
        "content_pages": len([page for page in pages if page.kind == "content"]),
        "ending_pages": len([page for page in pages if page.kind == "ending"]),
        "render_series_limit": max(0, args.render_series_limit),
        "cover_prompt": str(cover_prompt_path) if cover_prompt_path else "",
        "series_prompts": [str(path) for path in series_prompt_paths],
        "outline": str(outline_output),
        "cover_image": str(generated_cover) if generated_cover else "",
        "series_images": [str(path) for path in generated_series],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
