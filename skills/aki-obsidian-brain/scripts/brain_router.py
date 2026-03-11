#!/usr/bin/env python3
"""
Aki Obsidian Brain Router

Parse natural-language intent and read/write the configured Obsidian content system files.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

TASK_KEYWORDS = r"(任务|待办|todo|to[- ]?do|图度)"
IDEA_KEYWORDS = r"(灵感|想法|随手记)"
TOPIC_KEYWORDS = r"(选题|话题)"

TASK_PREFIX_PATTERNS = [
    rf"^(记个?|添加|加|记录)?\s*{TASK_KEYWORDS}\s*[:：]?\s*",
    rf"^我有(一个|个)?\s*{TASK_KEYWORDS}\s*[:：]?\s*",
    rf"^需要(一个|个)?\s*{TASK_KEYWORDS}\s*[:：]?\s*",
]

IDEA_PREFIX_PATTERNS = [
    rf"^(记个?|添加|加|记录)?\s*{IDEA_KEYWORDS}\s*[:：]?\s*",
    rf"^我有(一个|个)?\s*{IDEA_KEYWORDS}\s*[:：]?\s*",
    rf"^想到(一个|个)?\s*{IDEA_KEYWORDS}?\s*[:：]?\s*",
]

TOPIC_PREFIX_PATTERNS = [
    rf"^(记个?|添加|加|记录)?\s*{TOPIC_KEYWORDS}\s*[:：]?\s*",
    rf"^我有(一个|个)?\s*{TOPIC_KEYWORDS}\s*[:：]?\s*",
    rf"^我想写(一个|个)?\s*{TOPIC_KEYWORDS}\s*[:：]?\s*",
]

TASK_CAPTURE_PATTERNS = [
    rf"(记个?|添加|加|记录)?\s*{TASK_KEYWORDS}",
    rf"我有(一个|个)?\s*{TASK_KEYWORDS}",
    rf"需要(一个|个)?\s*{TASK_KEYWORDS}",
]

IDEA_CAPTURE_PATTERNS = [
    rf"(记个?|添加|加|记录)?\s*{IDEA_KEYWORDS}",
    rf"我有(一个|个)?\s*{IDEA_KEYWORDS}",
    rf"想到(一个|个)?\s*{IDEA_KEYWORDS}?",
]

TOPIC_CAPTURE_PATTERNS = [
    rf"(记个?|添加|加|记录)?\s*{TOPIC_KEYWORDS}",
    rf"我有(一个|个)?\s*{TOPIC_KEYWORDS}",
    rf"我想写(一个|个)?\s*{TOPIC_KEYWORDS}",
]


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def load_config(path: Path) -> Dict:
    if not path.exists():
        raise SystemExit(f"Config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_topic_title(title: str) -> str:
    s = normalize_spaces(title)
    s = re.sub(r"（\s*引用[:：].*?）\s*$", "", s)
    s = re.sub(r"\(\s*引用[:：].*?\)\s*$", "", s)
    return s.strip(" ，,。；;：:")


def extract_first_url(text: str) -> Optional[str]:
    m = re.search(r"https?://[^\s)]+", text)
    return m.group(0) if m else None


def clean_prefix(text: str, pattern: str) -> str:
    return re.sub(pattern, "", text, count=1).strip()


def strip_leading_patterns(text: str, patterns: List[str]) -> str:
    result = text.strip()
    for pattern in patterns:
        candidate = re.sub(pattern, "", result, count=1, flags=re.IGNORECASE).strip()
        if candidate != result:
            return candidate
    return result


def strip_after_keywords(text: str, keywords: List[str]) -> str:
    result = text
    for kw in keywords:
        idx = result.find(kw)
        if idx != -1:
            result = result[:idx]
    return result.strip(" ，,。；;：:")


def parse_topic_parts(raw: str) -> Tuple[str, Optional[str], Optional[str]]:
    content = strip_leading_patterns(raw, TOPIC_PREFIX_PATTERNS)

    source = extract_first_url(content)

    motive = None
    mm = re.search(r"动机\s*[:：]\s*(.+)$", content)
    if mm:
        motive = normalize_spaces(mm.group(1))

    title = content
    title = re.sub(r"来源\s*[:：]?", "", title)
    if source:
        title = title.replace(source, "")
    title = re.sub(r"动机\s*[:：].*$", "", title)
    title = strip_after_keywords(title, ["来源", "动机"])
    title = normalize_topic_title(title)

    return title, source, motive


def detect_task_quadrant(text: str, default_quadrant: str) -> str:
    s = text
    explicit = re.search(r"\bQ([1-4])\b", s, re.IGNORECASE)
    if explicit:
        return f"Q{explicit.group(1)}"

    if "重要且紧急" in s or "紧急且重要" in s:
        return "Q1"
    if "重要不紧急" in s or "不紧急但重要" in s:
        return "Q2"
    if "紧急不重要" in s or "不重要但紧急" in s:
        return "Q3"
    if "不紧急不重要" in s:
        return "Q4"

    has_important = "重要" in s and "不重要" not in s
    has_urgent = "紧急" in s and "不紧急" not in s
    if has_important and has_urgent:
        return "Q1"
    if has_important and ("不紧急" in s or not has_urgent):
        return "Q2"
    if has_urgent and "不重要" in s:
        return "Q3"

    return default_quadrant


def parse_task_content(raw: str) -> str:
    text = strip_leading_patterns(raw, TASK_PREFIX_PATTERNS)
    text = strip_after_keywords(
        text,
        [
            "重要且紧急",
            "紧急且重要",
            "重要不紧急",
            "不紧急但重要",
            "紧急不重要",
            "不重要但紧急",
            "不紧急不重要",
            "Q1",
            "Q2",
            "Q3",
            "Q4",
        ],
    )
    return normalize_spaces(text)


def parse_idea_content(raw: str) -> str:
    text = strip_leading_patterns(raw, IDEA_PREFIX_PATTERNS)
    return normalize_spaces(text)


def ensure_file(path: Path, header: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(header, encoding="utf-8")


def heal_literal_newlines(path: Path) -> None:
    """
    Repair legacy files where "\\n" was written as literal text in template headers.
    """
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    if "\\n" not in text:
        return

    first_line = text.splitlines()[0] if text else ""
    if first_line.startswith("# ") and "\\n" in first_line:
        path.write_text(text.replace("\\n", "\n"), encoding="utf-8")


def strip_duplicate_title_heading(path: Path) -> None:
    """
    Remove top-level heading when it duplicates Obsidian inline title (file stem).
    """
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return

    first = lines[0].strip()
    expected = f"# {path.stem}"
    if first != expected:
        return

    rest = lines[1:]
    while rest and rest[0].strip() == "":
        rest = rest[1:]
    output = "\n".join(rest).rstrip() + ("\n" if rest else "")
    path.write_text(output, encoding="utf-8")


def append_line(path: Path, line: str) -> None:
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    if content and not content.endswith("\n"):
        content += "\n"
    content += f"{line}\n"
    path.write_text(content, encoding="utf-8")


def parse_title_from_topic_line(line: str) -> str:
    s = re.sub(r"^- \[[ xX]\]\s*", "", line).strip()
    return normalize_topic_title(s.split("｜", 1)[0].strip())


def update_or_append_topic(path: Path, title: str, source: Optional[str], motive: Optional[str]) -> Dict:
    lines = path.read_text(encoding="utf-8").splitlines()

    for idx, line in enumerate(lines):
        if not re.match(r"^- \[[ xX]\]\s+", line):
            continue
        existing_title = parse_title_from_topic_line(line)
        if existing_title != title:
            continue

        changed = False
        new_line = line

        if source:
            if source not in new_line and "原文链接" not in new_line:
                new_line += f"｜引用: [原文链接]({source})"
                changed = True
            elif source not in new_line and "原文链接" in new_line:
                new_line += f"｜补充引用: [补充链接]({source})"
                changed = True

        if motive and "｜动机:" not in new_line:
            new_line += f"｜动机: {motive}"
            changed = True

        if changed:
            lines[idx] = new_line
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        return {
            "status": "updated" if changed else "unchanged",
            "title": title,
            "line": lines[idx],
            "file": str(path),
        }

    record = f"- [ ] {title}｜记录: {now_str()}｜标签: #topic #ai-tech"
    if source:
        record += f"｜引用: [原文链接]({source})"
    if motive:
        record += f"｜动机: {motive}"
    lines.append(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "status": "appended",
        "title": title,
        "line": record,
        "file": str(path),
    }


def pending_tasks_by_quadrant(path: Path) -> Dict[str, List[str]]:
    grouped = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    if not path.exists():
        return grouped

    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^- \[ \] \[(Q[1-4])\]\s+(.+)$", line)
        if m:
            grouped[m.group(1)].append(line)
    return grouped


def pending_topics(path: Path) -> List[str]:
    if not path.exists():
        return []
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if re.match(r"^- \[ \]\s+", line)
    ]


def trace_topic(path: Path, query: str) -> Dict:
    if not path.exists():
        return {"status": "not_found", "message": "选题库文件不存在"}

    lines = path.read_text(encoding="utf-8").splitlines()
    exact = None
    fuzzy = None
    normalized_query = normalize_topic_title(query)
    for line in lines:
        if not re.match(r"^- \[[ xX]\]\s+", line):
            continue
        title = parse_title_from_topic_line(line)
        if title == normalized_query:
            exact = line
            break
        if normalized_query in title and fuzzy is None:
            fuzzy = line

    line = exact or fuzzy
    if not line:
        return {"status": "not_found", "query": query}

    parts = [p.strip() for p in line.split("｜")]
    title = parse_title_from_topic_line(parts[0])

    result = {
        "status": "found",
        "query": normalized_query,
        "title": title,
        "raw": line,
        "recorded_at": None,
        "source": None,
        "motive": None,
    }

    for p in parts[1:]:
        if p.startswith("记录:"):
            result["recorded_at"] = p.replace("记录:", "", 1).strip()
        elif "原文链接" in p or "补充链接" in p:
            result["source"] = p
        elif p.startswith("动机:"):
            result["motive"] = p.replace("动机:", "", 1).strip()

    return result


def classify_intent(text: str) -> str:
    s = text.strip()
    lower = s.lower()

    if "追溯选题" in s:
        return "query_trace_topic"
    if "最重要的待办" in s:
        return "query_tasks_top"
    if "最重要的todo" in lower or "最重要的 to do" in lower:
        return "query_tasks_top"
    if "还有哪些没做" in s or "待办还有哪些" in s:
        return "query_tasks_pending"
    if "todo还有哪些" in lower or "to do还有哪些" in lower:
        return "query_tasks_pending"
    if "还有哪些话题没写" in s or "可写选题" in s:
        return "query_topics_pending"

    if any(re.search(pattern, s, re.IGNORECASE) for pattern in TASK_CAPTURE_PATTERNS):
        return "capture_task"
    if any(re.search(pattern, s, re.IGNORECASE) for pattern in IDEA_CAPTURE_PATTERNS):
        return "capture_idea"
    if any(re.search(pattern, s, re.IGNORECASE) for pattern in TOPIC_CAPTURE_PATTERNS):
        return "capture_topic"

    return "need_confirmation"


def append_log(path: Path, action: str, text: str, status: str) -> None:
    line = f"- {now_str()}｜{action}｜{status}｜{text}"
    append_line(path, line)


def main() -> None:
    parser = argparse.ArgumentParser(description="Aki Obsidian Brain Router")
    parser.add_argument("--input", "-i", help="Natural language input")
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "config.json"))
    parser.add_argument("--init-only", action="store_true", help="Initialize content system files only")
    args = parser.parse_args()

    cfg = load_config(Path(args.config).expanduser().resolve())
    vault_path = Path(cfg["vault_path"]).expanduser().resolve()
    system_dir = vault_path / cfg["system_dir"]
    files = cfg["files"]
    defaults = cfg.get("defaults", {})

    file_paths = {k: system_dir / v for k, v in files.items()}

    headers = {
        "tasks": "# 任务清单\n\n",
        "ideas": "# 灵感池\n\n",
        "topics": "# 选题库\n\n",
        "profile": "# 个人资料\n\n## 基本信息\n\n## 长期目标\n\n## 约束与偏好\n\n",
        "assets": "# 创作积累\n\n## 文章\n\n## 口播\n\n## 复盘\n\n",
        "media": "# 多媒体索引\n\n## 图片\n\n## 视频\n\n## 音频\n\n",
        "log": "# 操作日志\n\n",
    }

    for key, path in file_paths.items():
        ensure_file(path, headers.get(key, "# 文件\n\n"))
        heal_literal_newlines(path)
        strip_duplicate_title_heading(path)

    if args.init_only:
        print(json.dumps({"status": "initialized", "system_dir": str(system_dir)}, ensure_ascii=False, indent=2))
        return

    if not args.input:
        raise SystemExit("--input is required unless --init-only is used")

    text = normalize_spaces(args.input)
    intent = classify_intent(text)

    if intent == "need_confirmation":
        out = {
            "status": "need_confirmation",
            "message": "无法确定是任务/灵感/选题/查询，请补充意图关键词。",
            "candidates": ["记任务", "记灵感", "记选题", "还有哪些没做", "追溯选题"],
            "input": text,
        }
        append_log(file_paths["log"], intent, text, out["status"])
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if intent == "capture_task":
        quadrant = detect_task_quadrant(text, defaults.get("task_quadrant", "Q2"))
        content = parse_task_content(text)
        if not content:
            out = {"status": "need_confirmation", "message": "任务内容为空，请补充任务描述", "input": text}
        else:
            tag = quadrant.lower()
            line = f"- [ ] [{quadrant}] {content}｜记录: {now_str()}｜标签: #todo #{tag}"
            append_line(file_paths["tasks"], line)
            out = {"status": "appended", "intent": intent, "file": str(file_paths["tasks"]), "line": line}

    elif intent == "capture_idea":
        content = parse_idea_content(text)
        if not content:
            out = {"status": "need_confirmation", "message": "灵感内容为空，请补充", "input": text}
        else:
            line = f"- [ ] {content}｜记录: {now_str()}｜标签: #idea"
            append_line(file_paths["ideas"], line)
            out = {"status": "appended", "intent": intent, "file": str(file_paths["ideas"]), "line": line}

    elif intent == "capture_topic":
        title, source, motive = parse_topic_parts(text)
        if not title:
            out = {"status": "need_confirmation", "message": "选题标题为空，请补充", "input": text}
        else:
            out = {"intent": intent}
            out.update(update_or_append_topic(file_paths["topics"], title, source, motive))

    elif intent == "query_tasks_pending":
        grouped = pending_tasks_by_quadrant(file_paths["tasks"])
        out = {"status": "ok", "intent": intent, "grouped": grouped}

    elif intent == "query_tasks_top":
        grouped = pending_tasks_by_quadrant(file_paths["tasks"])
        top = (grouped["Q1"] + grouped["Q2"])[:10]
        out = {"status": "ok", "intent": intent, "top": top, "count": len(top)}

    elif intent == "query_topics_pending":
        items = pending_topics(file_paths["topics"])
        out = {"status": "ok", "intent": intent, "items": items, "count": len(items)}

    elif intent == "query_trace_topic":
        q = clean_prefix(text, r"^追溯选题\s*")
        out = {"intent": intent}
        out.update(trace_topic(file_paths["topics"], q))

    else:
        out = {"status": "need_confirmation", "message": "未匹配到可执行意图", "input": text}

    append_log(file_paths["log"], intent, text, out.get("status", "ok"))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
