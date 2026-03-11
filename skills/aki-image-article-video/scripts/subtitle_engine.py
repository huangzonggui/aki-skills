#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SENTENCE_PUNCT = set("。！？!?")
COMMA_PUNCT = set("，,；;：:")
SPLIT_PUNCT = SENTENCE_PUNCT | COMMA_PUNCT


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _srt_ts(sec: float) -> str:
    total_ms = max(0, int(round(sec * 1000.0)))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _write_srt(path: Path, segments: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{_srt_ts(seg['start'])} --> {_srt_ts(seg['end'])}")
        lines.append(seg["text"] or " ")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _run_whisper_json(audio_path: Path, model: str, language: str) -> dict[str, Any]:
    whisper_bin = shutil.which("whisper")
    if not whisper_bin:
        raise RuntimeError("whisper command not found in PATH")

    with tempfile.TemporaryDirectory(prefix="aki-subtitle-whisper-") as tmpdir:
        out_dir = Path(tmpdir)
        _run(
            [
                whisper_bin,
                str(audio_path),
                "--model",
                model,
                "--task",
                "transcribe",
                "--language",
                language,
                "--output_dir",
                str(out_dir),
                "--output_format",
                "json",
                "--word_timestamps",
                "True",
                "--verbose",
                "False",
                "--fp16",
                "False",
            ]
        )
        out_json = out_dir / f"{audio_path.stem}.json"
        if not out_json.exists():
            raise RuntimeError(f"whisper output json missing: {out_json}")
        return json.loads(out_json.read_text(encoding="utf-8"))


def _extract_asr_char_timeline(whisper_json: dict[str, Any]) -> tuple[list[dict[str, Any]], list[float], float]:
    chars: list[dict[str, Any]] = []
    boundaries: list[float] = []
    max_end = 0.0

    segments = whisper_json.get("segments") or []
    for seg in segments:
        seg_start = float(seg.get("start", 0.0) or 0.0)
        seg_end = float(seg.get("end", seg_start) or seg_start)
        words = seg.get("words") or []

        if words:
            for w in words:
                raw = str(w.get("word") or "")
                token = re.sub(r"\s+", "", raw)
                if not token:
                    continue
                w_start = float(w.get("start", seg_start) or seg_start)
                w_end = float(w.get("end", max(w_start + 0.01, seg_end)) or max(w_start + 0.01, seg_end))
                if w_end < w_start:
                    w_end = w_start + 0.01
                max_end = max(max_end, w_end)
                boundaries.extend([w_start, w_end])
                span = max(0.01, w_end - w_start)
                unit = span / max(1, len(token))
                for i, ch in enumerate(token):
                    c_st = w_start + unit * i
                    c_ed = min(w_end, w_start + unit * (i + 1))
                    if c_ed <= c_st:
                        c_ed = c_st + 0.01
                    chars.append({"char": ch, "start": c_st, "end": c_ed, "center": (c_st + c_ed) * 0.5})
        else:
            raw = str(seg.get("text") or "")
            token = re.sub(r"\s+", "", raw)
            if not token:
                continue
            if seg_end < seg_start:
                seg_end = seg_start + 0.01
            max_end = max(max_end, seg_end)
            boundaries.extend([seg_start, seg_end])
            span = max(0.01, seg_end - seg_start)
            unit = span / max(1, len(token))
            for i, ch in enumerate(token):
                c_st = seg_start + unit * i
                c_ed = min(seg_end, seg_start + unit * (i + 1))
                if c_ed <= c_st:
                    c_ed = c_st + 0.01
                chars.append({"char": ch, "start": c_st, "end": c_ed, "center": (c_st + c_ed) * 0.5})

    boundaries = sorted(set(round(x, 3) for x in boundaries))
    return chars, boundaries, max_end


def _compact_script(script_text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, ch in enumerate(script_text):
        if ch.isspace():
            continue
        out.append({"char": ch, "orig_idx": idx})
    return out


def _align_script_char_times(
    script_chars: list[dict[str, Any]],
    asr_chars: list[dict[str, Any]],
    audio_end_sec: float,
) -> tuple[list[dict[str, Any]], float]:
    if not script_chars:
        return [], 1.0

    if not asr_chars:
        # fallback linear timeline when ASR chars unavailable
        total = len(script_chars)
        unit = max(0.02, audio_end_sec / max(1, total))
        out: list[dict[str, Any]] = []
        t = 0.0
        for item in script_chars:
            st = t
            ed = min(audio_end_sec, st + unit)
            out.append({**item, "start": st, "end": max(ed, st + 0.02)})
            t = ed
        return out, 0.0

    script_seq = "".join(x["char"] for x in script_chars)
    asr_seq = "".join(x["char"] for x in asr_chars)

    n = len(script_chars)
    start_map: list[float | None] = [None] * n
    end_map: list[float | None] = [None] * n

    matcher = difflib.SequenceMatcher(a=script_seq, b=asr_seq, autojunk=False)
    matched = 0
    for block in matcher.get_matching_blocks():
        if block.size <= 0:
            continue
        for k in range(block.size):
            si = block.a + k
            ai = block.b + k
            a_item = asr_chars[ai]
            start_map[si] = float(a_item["start"])
            end_map[si] = float(a_item["end"])
            matched += 1

    coverage = matched / max(1, n)

    known = [i for i, x in enumerate(start_map) if x is not None]
    if not known:
        unit = max(0.02, audio_end_sec / max(1, n))
        out = []
        t = 0.0
        for item in script_chars:
            st = t
            ed = min(audio_end_sec, st + unit)
            out.append({**item, "start": st, "end": max(ed, st + 0.02)})
            t = ed
        return out, coverage

    first_known = known[0]
    for i in range(first_known - 1, -1, -1):
        nxt = float(start_map[i + 1] or 0.0)
        st = max(0.0, nxt - 0.04)
        start_map[i] = st
        end_map[i] = max(st + 0.02, nxt - 0.001)

    for idx in range(len(known) - 1):
        left = known[idx]
        right = known[idx + 1]
        if right - left <= 1:
            continue
        l_end = float(end_map[left] or 0.0)
        r_start = float(start_map[right] or l_end + 0.02)
        if r_start <= l_end:
            r_start = l_end + 0.02
        span = r_start - l_end
        for i in range(left + 1, right):
            frac0 = (i - left) / (right - left)
            frac1 = (i - left + 1) / (right - left)
            st = l_end + span * frac0
            ed = l_end + span * frac1
            if ed <= st:
                ed = st + 0.02
            start_map[i] = st
            end_map[i] = ed

    last_known = known[-1]
    for i in range(last_known + 1, n):
        prv = float(end_map[i - 1] or 0.0)
        st = prv
        ed = min(audio_end_sec, st + 0.04)
        if ed <= st:
            ed = st + 0.02
        start_map[i] = st
        end_map[i] = ed

    out: list[dict[str, Any]] = []
    prev_end = 0.0
    for i, item in enumerate(script_chars):
        st = float(start_map[i] or prev_end)
        ed = float(end_map[i] or (st + 0.02))
        if st < prev_end:
            st = prev_end
        if ed <= st:
            ed = st + 0.02
        out.append({**item, "start": st, "end": ed})
        prev_end = ed

    return out, coverage


def _find_split_index(chars: list[dict[str, Any]], st: int, ed: int, punct: set[str], preferred: int) -> int | None:
    if ed - st < 2:
        return None
    left = max(st + 1, preferred - 12)
    right = min(ed - 1, preferred + 12)

    best: int | None = None
    best_dist = 10**9
    for i in range(left, right + 1):
        if chars[i]["char"] in punct:
            dist = abs(i - preferred)
            if dist < best_dist:
                best = i
                best_dist = dist
    return best


def _is_ascii_word_char(ch: str) -> bool:
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9")


def _is_bad_split(chars: list[dict[str, Any]], idx: int) -> bool:
    if idx <= 0 or idx >= len(chars) - 1:
        return False
    left = str(chars[idx]["char"])
    right = str(chars[idx + 1]["char"])
    if _is_ascii_word_char(left) and _is_ascii_word_char(right):
        return True
    if left == "·" or right == "·":
        return True
    return False


def _adjust_split_index(chars: list[dict[str, Any]], st: int, ed: int, cut: int) -> int:
    cut = max(st + 1, min(ed - 1, cut))
    if not _is_bad_split(chars, cut):
        return cut
    max_probe = min(12, ed - st - 1)
    for offset in range(1, max_probe + 1):
        left = cut - offset
        if left > st and not _is_bad_split(chars, left):
            return left
        right = cut + offset
        if right < ed and not _is_bad_split(chars, right):
            return right
    return cut


def _base_segments(chars: list[dict[str, Any]], gap_sec: float) -> list[tuple[int, int]]:
    if not chars:
        return []
    out: list[tuple[int, int]] = []
    st = 0
    for i in range(len(chars) - 1):
        c = chars[i]["char"]
        gap = float(chars[i + 1]["start"] - chars[i]["end"])
        if c in SENTENCE_PUNCT:
            out.append((st, i))
            st = i + 1
        elif gap >= gap_sec and i >= st:
            out.append((st, i))
            st = i + 1
    if st <= len(chars) - 1:
        out.append((st, len(chars) - 1))
    return out


def _refine_segments(
    chars: list[dict[str, Any]],
    initial: list[tuple[int, int]],
    max_chars: int,
    max_duration: float,
    comma_min_chars: int,
) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for seg in initial:
        stack = [seg]
        while stack:
            st, ed = stack.pop()
            if ed < st:
                continue
            seg_len = ed - st + 1
            seg_dur = float(chars[ed]["end"] - chars[st]["start"])

            # stable-ts style: long segment -> comma split first
            if seg_len >= comma_min_chars:
                mid = (st + ed) // 2
                cut = _find_split_index(chars, st, ed, COMMA_PUNCT, mid)
                if cut is not None and cut > st and cut < ed:
                    stack.append((cut + 1, ed))
                    stack.append((st, cut))
                    continue

            if seg_len > max_chars or seg_dur > max_duration:
                mid = (st + ed) // 2
                cut = _find_split_index(chars, st, ed, SPLIT_PUNCT, mid)
                if cut is None:
                    cut = mid
                if cut <= st:
                    cut = st + max(1, min(max_chars - 1, (ed - st) // 2))
                if cut >= ed:
                    cut = ed - 1
                cut = _adjust_split_index(chars, st, ed, cut)
                if cut > st and cut < ed:
                    stack.append((cut + 1, ed))
                    stack.append((st, cut))
                    continue

            out.append((st, ed))

    out.sort(key=lambda x: x[0])
    # merge accidental tiny segments
    merged: list[tuple[int, int]] = []
    for st, ed in out:
        if not merged:
            merged.append((st, ed))
            continue
        pst, ped = merged[-1]
        if ed - st + 1 <= 1:
            merged[-1] = (pst, ed)
        else:
            merged.append((st, ed))
    return merged


def _segments_to_srt(
    script_text: str,
    chars: list[dict[str, Any]],
    segments: list[tuple[int, int]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    prev_end = 0.0
    for st, ed in segments:
        o_st = int(chars[st]["orig_idx"])
        o_ed = int(chars[ed]["orig_idx"])
        text = script_text[o_st : o_ed + 1]
        text = re.sub(r"\s+", "", text)
        if not text:
            text = "".join(x["char"] for x in chars[st : ed + 1])

        seg_st = float(chars[st]["start"])
        seg_ed = float(chars[ed]["end"])
        if seg_st < prev_end:
            seg_st = prev_end
        if seg_ed <= seg_st:
            seg_ed = seg_st + 0.08

        out.append({"start": seg_st, "end": seg_ed, "text": text, "char_len": len(text)})
        prev_end = seg_ed
    return out


def _nearest_boundary_error_ms(value: float, boundaries: list[float]) -> float:
    if not boundaries:
        return 0.0
    # boundaries are sorted, small list -> simple min is fine
    return min(abs(value - b) for b in boundaries) * 1000.0


def _calc_report(
    srt_segments: list[dict[str, Any]],
    boundaries: list[float],
    coverage_ratio: float,
    max_chars: int,
    max_duration: float,
) -> dict[str, Any]:
    errors: list[float] = []
    overlong = 0
    for seg in srt_segments:
        st = float(seg["start"])
        ed = float(seg["end"])
        ln = int(seg.get("char_len", len(seg.get("text", ""))))
        dur = max(0.0, ed - st)
        errors.append(_nearest_boundary_error_ms(st, boundaries))
        errors.append(_nearest_boundary_error_ms(ed, boundaries))
        if ln > max_chars or dur > max_duration:
            overlong += 1

    avg = sum(errors) / max(1, len(errors))
    sorted_err = sorted(errors)
    p95_idx = max(0, math.ceil(len(sorted_err) * 0.95) - 1)
    p95 = sorted_err[p95_idx] if sorted_err else 0.0

    return {
        "segment_count": len(srt_segments),
        "avg_boundary_error_ms": round(avg, 3),
        "p95_boundary_error_ms": round(p95, 3),
        "overlong_ratio": round(overlong / max(1, len(srt_segments)), 6),
        "coverage_ratio": round(float(coverage_ratio), 6),
        "retry_used": False,
    }


def _qa_pass(report: dict[str, Any], policy: str) -> bool:
    if policy == "off":
        return True
    if policy == "medium":
        return (
            report["coverage_ratio"] >= 0.98
            and report["avg_boundary_error_ms"] <= 320
            and report["p95_boundary_error_ms"] <= 700
            and report["overlong_ratio"] <= 0.08
        )
    # strict
    return (
        report["coverage_ratio"] >= 0.995
        and report["avg_boundary_error_ms"] <= 220
        and report["p95_boundary_error_ms"] <= 450
        and report["overlong_ratio"] <= 0.03
    )


def _build_once(
    script_text: str,
    aligned_chars: list[dict[str, Any]],
    boundaries: list[float],
    *,
    gap_sec: float,
    max_chars: int,
    max_duration: float,
    comma_min_chars: int,
    coverage_ratio: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base = _base_segments(aligned_chars, gap_sec=gap_sec)
    refined = _refine_segments(
        aligned_chars,
        initial=base,
        max_chars=max_chars,
        max_duration=max_duration,
        comma_min_chars=comma_min_chars,
    )
    srt_segments = _segments_to_srt(script_text=script_text, chars=aligned_chars, segments=refined)
    report = _calc_report(
        srt_segments=srt_segments,
        boundaries=boundaries,
        coverage_ratio=coverage_ratio,
        max_chars=max_chars,
        max_duration=max_duration,
    )
    return srt_segments, report


def generate_aligned_srt(
    audio_path: Path,
    script_text: str,
    output_srt: Path,
    *,
    whisper_model: str = "small",
    whisper_language: str = "zh",
    qa_policy: str = "strict",
    max_chars: int = 26,
    max_duration: float = 3.2,
    gap_sec: float = 0.5,
    comma_min_chars: int = 50,
) -> dict[str, Any]:
    whisper_json = _run_whisper_json(audio_path=audio_path, model=whisper_model, language=whisper_language)
    asr_chars, boundaries, audio_end = _extract_asr_char_timeline(whisper_json)

    compact_script = _compact_script(script_text)
    if not compact_script:
        raise RuntimeError("script text is empty after compaction")

    aligned_chars, coverage_ratio = _align_script_char_times(
        script_chars=compact_script,
        asr_chars=asr_chars,
        audio_end_sec=max(audio_end, 0.5),
    )

    srt_segments, report = _build_once(
        script_text=script_text,
        aligned_chars=aligned_chars,
        boundaries=boundaries,
        gap_sec=gap_sec,
        max_chars=max_chars,
        max_duration=max_duration,
        comma_min_chars=comma_min_chars,
        coverage_ratio=coverage_ratio,
    )

    warnings: list[str] = []
    if qa_policy in ("strict", "medium") and not _qa_pass(report, qa_policy):
        retry_segments, retry_report = _build_once(
            script_text=script_text,
            aligned_chars=aligned_chars,
            boundaries=boundaries,
            gap_sec=max(0.3, gap_sec * 0.7),
            max_chars=max(16, max_chars - 4),
            max_duration=max(2.0, max_duration - 0.6),
            comma_min_chars=max(24, comma_min_chars - 15),
            coverage_ratio=coverage_ratio,
        )
        retry_report["retry_used"] = True
        srt_segments = retry_segments
        report = retry_report
        if not _qa_pass(report, qa_policy):
            warnings.append("subtitle QA still below threshold after retry")

    _write_srt(output_srt, srt_segments)

    return {
        "srt_path": str(output_srt),
        "report": report,
        "warnings": warnings,
        "engine": "stable_regroup",
        "whisper_model": whisper_model,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate aligned SRT using whisper word timestamps + regroup")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--output-srt", required=True)
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--whisper-language", default="zh")
    parser.add_argument("--qa-policy", choices=["strict", "medium", "off"], default="strict")
    parser.add_argument("--max-chars", type=int, default=26)
    parser.add_argument("--max-duration", type=float, default=3.2)
    parser.add_argument("--gap-sec", type=float, default=0.5)
    parser.add_argument("--comma-min-chars", type=int, default=50)
    parser.add_argument("--json-report", default="")
    args = parser.parse_args()

    script_path = Path(args.script).expanduser().resolve()
    audio_path = Path(args.audio).expanduser().resolve()
    output_srt = Path(args.output_srt).expanduser().resolve()

    script_text = script_path.read_text(encoding="utf-8", errors="ignore")
    res = generate_aligned_srt(
        audio_path=audio_path,
        script_text=script_text,
        output_srt=output_srt,
        whisper_model=args.whisper_model,
        whisper_language=args.whisper_language,
        qa_policy=args.qa_policy,
        max_chars=args.max_chars,
        max_duration=args.max_duration,
        gap_sec=args.gap_sec,
        comma_min_chars=args.comma_min_chars,
    )

    if args.json_report:
        rp = Path(args.json_report).expanduser().resolve()
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
