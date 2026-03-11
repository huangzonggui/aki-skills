#!/usr/bin/env python3
"""
Parse a Coze workflow export JSON (.txt) and produce a skill blueprint markdown.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Tuple

TYPE_LABEL = {
    "1": "Start",
    "2": "End",
    "3": "LLM",
    "4": "Plugin",
    "5": "Code",
    "8": "Selector",
    "13": "Output",
    "15": "TextProcess",
    "21": "Loop",
    "23": "ImageGenerate",
    "28": "PromptGenerate",
    "31": "Comment",
    "32": "VariableMerge",
}


def safe_title(node: dict) -> str:
    title = (
        node.get("data", {})
        .get("nodeMeta", {})
        .get("title")
    )
    if title:
        return title
    return f"Node-{node.get('id')}"


def type_name(type_id: str) -> str:
    return TYPE_LABEL.get(type_id, f"Type-{type_id}")


def build_graph(nodes: List[dict], edges: List[dict]) -> Tuple[Dict[str, List[str]], Dict[str, int]]:
    node_ids = {str(n.get("id")) for n in nodes}
    adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}
    indeg: Dict[str, int] = {nid: 0 for nid in node_ids}

    for e in edges:
        s = str(e.get("sourceNodeID"))
        t = str(e.get("targetNodeID"))
        if s in adj and t in indeg:
            adj[s].append(t)
            indeg[t] += 1

    return adj, indeg


def topo_sort(nodes: List[dict], edges: List[dict]) -> List[str]:
    adj, indeg = build_graph(nodes, edges)
    q = deque([nid for nid, d in indeg.items() if d == 0])
    ordered: List[str] = []

    while q:
        cur = q.popleft()
        ordered.append(cur)
        for nxt in adj[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)

    if len(ordered) != len(indeg):
        # fallback deterministic order if graph has cycles
        missing = [nid for nid in indeg if nid not in ordered]
        ordered.extend(sorted(missing))
    return ordered


def node_phase(title: str, ntype: str) -> str:
    t = title.lower()
    if ntype == "1":
        return "启动与输入"
    if ntype == "2":
        return "结束与输出"
    if "文案" in title and ("生成" in title or ntype == "3"):
        return "文案生成"
    if "分镜" in title or "画面" in title:
        return "分镜规划"
    if "图片" in title or "背景图" in title:
        return "图片生成"
    if "创建草稿" in title or "剪映" in title:
        return "剪映编排"
    if "字幕" in title or "caption" in t:
        return "字幕处理"
    if "配音" in title or "音频" in title or "音乐" in title:
        return "音频处理"
    if ntype in {"21", "32", "5", "8", "15"}:
        return "控制与数据处理"
    if ntype == "13":
        return "状态回传"
    return "其他"


def infer_skill_modules(nodes: List[dict]) -> List[Tuple[str, str, str]]:
    titles = [safe_title(n) for n in nodes]

    modules: List[Tuple[str, str, str]] = []
    modules.append((
        "输入标准化模块",
        "文章/已有文案/图片目录标准化为统一输入",
        "新增 `--coze-mode` 参数，支持从主题或文案直接进入分镜流程",
    ))

    if any("文案生成" in x or "LLM：文案生成" in x for x in titles):
        modules.append((
            "文案生成模块",
            "当未提供口播稿时先生成脚本",
            "复用已有 article-transformer；输出可直接用于 SRT/配音",
        ))

    if any("分镜" in x or "画面内容" in x for x in titles):
        modules.append((
            "分镜规划模块",
            "把脚本切分为镜头段并生成每段结构化时间线",
            "新增 `scripts/storyboard_from_script.py`（待实现）",
        ))

    if any("图片" in x for x in titles):
        modules.append((
            "图片生成与聚合模块",
            "批量生成/收集分镜图片并映射到时间轴",
            "新增 `scripts/collect_image_assets.py`（待实现）",
        ))

    modules.append((
        "剪映草稿编排模块",
        "创建新草稿并写入图片轨、字幕轨、转场与特效",
        "复用 `build_video_from_article_assets.py` + `jianying-editor`",
    ))

    modules.append((
        "可选音频模块",
        "配音与背景音乐按开关启用",
        "当前默认 `--skip-audio`，等待 MiniMax API 后接入",
    ))

    modules.append((
        "质检与索引模块",
        "检查丢失媒体、轨道完整性，并将草稿置顶",
        "保留 `root_meta_info.json` 注入逻辑",
    ))

    return modules


def generate_markdown(source_file: Path, payload: dict) -> str:
    src = payload.get("source", {})
    wf = payload.get("json", {})
    nodes: List[dict] = wf.get("nodes", [])
    edges: List[dict] = wf.get("edges", [])

    node_map = {str(n.get("id")): n for n in nodes}
    order = topo_sort(nodes, edges)

    type_count: Dict[str, int] = defaultdict(int)
    phase_count: Dict[str, int] = defaultdict(int)
    ordered_rows: List[Tuple[str, str, str, str]] = []

    for nid in order:
        n = node_map.get(nid)
        if not n:
            continue
        ntype = str(n.get("type"))
        title = safe_title(n)
        phase = node_phase(title, ntype)
        type_count[ntype] += 1
        phase_count[phase] += 1
        ordered_rows.append((nid, type_name(ntype), title, phase))

    modules = infer_skill_modules(nodes)

    lines: List[str] = []
    lines.append("# Coze Workflow -> Skill Blueprint")
    lines.append("")
    lines.append(f"- Source file: `{source_file}`")
    lines.append(f"- Workflow ID: `{src.get('workflowId', '')}`")
    lines.append(f"- Space ID: `{src.get('spaceId', '')}`")
    lines.append(f"- Nodes: `{len(nodes)}`")
    lines.append(f"- Edges: `{len(edges)}`")
    lines.append("")

    lines.append("## Node Types")
    for k, v in sorted(type_count.items(), key=lambda kv: kv[0]):
        lines.append(f"- `{k}` {type_name(k)}: {v}")
    lines.append("")

    lines.append("## Phase Distribution")
    for k, v in sorted(phase_count.items(), key=lambda kv: kv[0]):
        lines.append(f"- `{k}`: {v}")
    lines.append("")

    lines.append("## Ordered Flow (Topological)")
    lines.append("| # | NodeID | Type | Title | Phase |")
    lines.append("|---|---|---|---|---|")
    for i, (nid, tname, title, phase) in enumerate(ordered_rows, start=1):
        lines.append(f"| {i} | {nid} | {tname} | {title} | {phase} |")
    lines.append("")

    lines.append("## Skill Architecture Proposal (Non-TTS First)")
    for name, purpose, implement in modules:
        lines.append(f"- **{name}**")
        lines.append(f"  - Purpose: {purpose}")
        lines.append(f"  - Implementation: {implement}")
    lines.append("")

    lines.append("## Immediate Action Items")
    lines.append("- Keep current pipeline in non-TTS mode by default (`--skip-audio`).")
    lines.append("- Add storyboard splitter from script to structured timeline.")
    lines.append("- Add image collector to map generated images to timeline nodes.")
    lines.append("- Keep JianYing JSON patch and root index update as stable sink layer.")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate skill blueprint from Coze workflow export")
    parser.add_argument("--workflow-file", required=True, help="coze exported workflow json txt")
    parser.add_argument("--output", required=True, help="markdown output path")
    args = parser.parse_args()

    src = Path(args.workflow_file).expanduser().resolve()
    out = Path(args.output).expanduser().resolve()

    payload = json.loads(src.read_text(encoding="utf-8"))
    md = generate_markdown(src, payload)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"✅ blueprint written: {out}")


if __name__ == "__main__":
    main()
