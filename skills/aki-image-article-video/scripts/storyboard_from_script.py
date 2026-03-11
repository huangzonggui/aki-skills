#!/usr/bin/env python3
"""
Create storyboard timeline JSON from script text.
Non-TTS path: used before image assembly.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List


def clean_script(text: str) -> str:
    text = re.sub(r"^\s*#+\s*.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*时长\s*[:：].*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def split_sentences(text: str) -> List[str]:
    raw = re.split(r"[。！？!?；;\n]+", text)
    arr = [x.strip() for x in raw if x.strip()]
    return arr


def rebalance(sentences: List[str], target_segments: int) -> List[str]:
    if target_segments <= 0:
        return []
    if not sentences:
        return [""] * target_segments

    if len(sentences) <= target_segments:
        out = sentences[:]
        while len(out) < target_segments:
            out.append("")
        return out

    # merge sentence chunks by index
    chunks: List[List[str]] = [[] for _ in range(target_segments)]
    for i, s in enumerate(sentences):
        idx = int(i * target_segments / len(sentences))
        idx = min(max(idx, 0), target_segments - 1)
        chunks[idx].append(s)
    return ["，".join(x).strip("，") for x in chunks]


def allocate_durations(total_sec: float, weights: List[int]) -> List[float]:
    total_w = sum(weights) or 1
    raw = [total_sec * w / total_w for w in weights]
    # round to 3 decimals and normalize tail
    rounded = [round(x, 3) for x in raw]
    diff = round(total_sec - sum(rounded), 3)
    if rounded:
        rounded[-1] = round(rounded[-1] + diff, 3)
    return rounded


def main() -> None:
    parser = argparse.ArgumentParser(description="Create storyboard from script")
    parser.add_argument("--script", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--total-duration", type=float, default=30.0)
    parser.add_argument("--segments", type=int, default=4, help="cover + points count")
    parser.add_argument(
        "--labels",
        default="cover,point1,point2,point3",
        help="comma-separated segment labels",
    )
    args = parser.parse_args()

    script_path = Path(args.script).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    text = clean_script(script_path.read_text(encoding="utf-8"))
    sents = split_sentences(text)
    parts = rebalance(sents, args.segments)

    weights = [max(len(x), 8) for x in parts]
    durations = allocate_durations(args.total_duration, weights)

    labels = [x.strip() for x in args.labels.split(",") if x.strip()]
    while len(labels) < len(parts):
        labels.append(f"part{len(labels)+1}")

    timeline = []
    cursor = 0.0
    for i, (txt, dur) in enumerate(zip(parts, durations), start=1):
        start = round(cursor, 3)
        end = round(cursor + dur, 3)
        cursor = end
        timeline.append(
            {
                "index": i,
                "label": labels[i - 1],
                "text": txt,
                "start": start,
                "end": end,
                "duration": round(dur, 3),
            }
        )

    payload = {
        "script": str(script_path),
        "total_duration": args.total_duration,
        "segments": len(timeline),
        "timeline": timeline,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ storyboard written: {output_path}")


if __name__ == "__main__":
    main()
