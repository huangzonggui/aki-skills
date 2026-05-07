#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}
SEVERITY_LABEL = {"low": "低", "medium": "中", "high": "高"}


@dataclass(frozen=True)
class Rule:
    term: str
    severity: str
    category: str
    reason: str
    suggestions: list[str]
    mode: str = "literal"


@dataclass(frozen=True)
class Finding:
    file: Path
    line_no: int
    column: int
    term: str
    severity: str
    category: str
    reason: str
    suggestion: str
    line_text: str


def load_rules() -> list[Rule]:
    lexicon_path = Path(__file__).resolve().parents[1] / "references" / "risk-lexicon.zh.json"
    raw = json.loads(lexicon_path.read_text(encoding="utf-8"))
    rules: list[Rule] = []
    for item in raw.get("rules", []):
        rules.append(
            Rule(
                term=str(item["term"]),
                severity=str(item.get("severity") or "low"),
                category=str(item.get("category") or ""),
                reason=str(item.get("reason") or ""),
                suggestions=[str(v) for v in item.get("suggestions", [])],
                mode=str(item.get("mode") or "literal"),
            )
        )
    return sorted(rules, key=lambda r: (len(r.term), SEVERITY_RANK.get(r.severity, 0)), reverse=True)


def iter_matches(line: str, rule: Rule) -> list[tuple[int, int, str]]:
    if rule.mode == "regex":
        return [(m.start(), m.end(), m.group(0)) for m in re.finditer(rule.term, line)]
    matches: list[tuple[int, int, str]] = []
    start = 0
    while True:
        idx = line.find(rule.term, start)
        if idx < 0:
            break
        matches.append((idx, idx + len(rule.term), rule.term))
        start = idx + max(1, len(rule.term))
    return matches


def overlaps(span: tuple[int, int], used: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(start < old_end and end > old_start for old_start, old_end in used)


def scan_file(path: Path, rules: list[Rule], min_severity: str) -> list[Finding]:
    threshold = SEVERITY_RANK[min_severity]
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    for line_no, line in enumerate(text.splitlines(), start=1):
        used_spans: list[tuple[int, int]] = []
        for rule in rules:
            if SEVERITY_RANK.get(rule.severity, 0) < threshold:
                continue
            for start, end, matched in iter_matches(line, rule):
                if overlaps((start, end), used_spans):
                    continue
                used_spans.append((start, end))
                findings.append(
                    Finding(
                        file=path,
                        line_no=line_no,
                        column=start + 1,
                        term=matched,
                        severity=rule.severity,
                        category=rule.category,
                        reason=rule.reason,
                        suggestion=rule.suggestions[0] if rule.suggestions else "",
                        line_text=line.strip(),
                    )
                )
    return findings


def overall_risk(findings: list[Finding]) -> str:
    if not findings:
        return "clean"
    max_rank = max(SEVERITY_RANK.get(item.severity, 0) for item in findings)
    for severity, rank in SEVERITY_RANK.items():
        if rank == max_rank:
            return severity
    return "low"


def rewrite_text(text: str, rules: list[Rule], min_severity: str) -> str:
    threshold = SEVERITY_RANK[min_severity]
    rewritten = text
    for rule in rules:
        if SEVERITY_RANK.get(rule.severity, 0) < threshold or not rule.suggestions:
            continue
        replacement = rule.suggestions[0]
        if rule.mode == "regex":
            rewritten = re.sub(rule.term, replacement, rewritten)
        else:
            rewritten = rewritten.replace(rule.term, replacement)
    return rewritten


def markdown_report(files: list[Path], findings: list[Finding], rules: list[Rule], args: argparse.Namespace) -> str:
    risk = overall_risk(findings)
    lines = [
        "# Domestic Platform Risk Check",
        "",
        f"- Platform: {args.platform}",
        f"- Overall risk: {risk}",
        f"- Findings: {len(findings)}",
        "",
    ]
    if findings:
        lines.extend(
            [
                "| File | Line | Word | Risk | Category | Suggestion | Why |",
                "|---|---:|---|---|---|---|---|",
            ]
        )
        for item in findings:
            suggestion = item.suggestion or "-"
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(item.file),
                        str(item.line_no),
                        f"`{item.term}`",
                        SEVERITY_LABEL.get(item.severity, item.severity),
                        item.category,
                        suggestion,
                        item.reason,
                    ]
                )
                + " |"
            )
    else:
        lines.append("No configured risk words found.")

    if args.rewrite:
        for path in files:
            original = path.read_text(encoding="utf-8", errors="ignore")
            rewritten = rewrite_text(original, rules, args.min_severity)
            if rewritten == original:
                continue
            lines.extend(
                [
                    "",
                    f"## Safer Rewrite: {path}",
                    "",
                    "```md",
                    rewritten.strip(),
                    "```",
                ]
            )
    lines.extend(
        [
            "",
            "> Note: This is a non-official preflight check. Platform moderation rules change; use judgment for facts, quotes, and news context.",
        ]
    )
    return "\n".join(lines) + "\n"


def json_report(findings: list[Finding], args: argparse.Namespace) -> str:
    data: dict[str, Any] = {
        "platform": args.platform,
        "overall_risk": overall_risk(findings),
        "findings": [
            {
                "file": str(item.file),
                "line": item.line_no,
                "column": item.column,
                "term": item.term,
                "severity": item.severity,
                "category": item.category,
                "suggestion": item.suggestion,
                "reason": item.reason,
                "line_text": item.line_text,
            }
            for item in findings
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Chinese self-media drafts for domestic platform risk words.")
    parser.add_argument("files", nargs="+", help="Markdown/text files to scan.")
    parser.add_argument(
        "--platform",
        default="xiaohongshu",
        choices=["all", "xiaohongshu", "douyin", "wechat", "video-account", "bilibili"],
        help="Platform context for the report. Current lexicon is shared across platforms.",
    )
    parser.add_argument(
        "--min-severity",
        default="low",
        choices=["low", "medium", "high"],
        help="Minimum severity to report.",
    )
    parser.add_argument("--rewrite", action="store_true", help="Include a safer rewrite using first-choice replacements.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--fail-on", choices=["none", "low", "medium", "high"], default="none")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files = [Path(item).expanduser().resolve() for item in args.files]
    missing = [path for path in files if not path.exists()]
    if missing:
        for path in missing:
            print(f"Missing file: {path}", file=sys.stderr)
        return 2

    rules = load_rules()
    findings: list[Finding] = []
    for path in files:
        findings.extend(scan_file(path, rules, args.min_severity))

    if args.format == "json":
        sys.stdout.write(json_report(findings, args))
    else:
        sys.stdout.write(markdown_report(files, findings, rules, args))

    if args.fail_on != "none":
        threshold = SEVERITY_RANK[args.fail_on]
        if any(SEVERITY_RANK.get(item.severity, 0) >= threshold for item in findings):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
