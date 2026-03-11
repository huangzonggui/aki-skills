#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from state import BLOCKED, DONE, FAILED, RUNNING, set_artifact, set_step
from utils import (
    best_effort_fetch,
    clean_text,
    detect_domain,
    ensure_dir,
    is_url,
    is_video_url,
    run,
    sanitize_title,
    slug_domain,
)


DEFAULT_WECHAT_FETCHER = Path(
    "/Users/aki/Development/code/aki-skills/skills/aki-wechat-fetcher/scripts/fetch.ts"
)
DEFAULT_YOUTUBE_RUNNER = Path(
    "/Users/aki/Development/code/aki-skills/skills/Youtube-clipper-skill/scripts/py"
)
DEFAULT_YOUTUBE_DOWNLOAD_SCRIPT = Path(
    "/Users/aki/Development/code/aki-skills/skills/Youtube-clipper-skill/scripts/download_video.py"
)
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "www.youtu.be"}
VTT_TIMECODE_RE = re.compile(
    r"^\d{2}:\d{2}(?::\d{2})?[.,]\d{3}\s+-->\s+\d{2}:\d{2}(?::\d{2})?[.,]\d{3}"
)


def _next_index(refs_dir: Path) -> int:
    existing = sorted(refs_dir.glob("*_raw.md"))
    return len(existing) + 1


def _extract_title_author(raw_text: str, source_tag: str) -> tuple[str, str]:
    title = ""
    author = ""
    for line in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        s = line.strip()
        if not s:
            continue
        if not title and s.startswith("# "):
            title = s[2:].strip()
            if title.lower() == "untitled":
                title = ""
            continue
        if not author:
            m = re.match(r"^\*\*作者\*\*[:：]\s*(.+)$", s)
            if m:
                author = re.sub(r"\s+", " ", m.group(1)).strip()
                continue
        if not title and not s.startswith("**") and s != "---" and "![" not in s:
            title = s[:80]
    if not title:
        title = source_tag or "untitled"
    if not author:
        author = "未知作者"
    return title, author


def _write_pair(refs_dir: Path, idx: int, source_tag: str, raw_text: str) -> tuple[Path, Path]:
    title, author = _extract_title_author(raw_text, source_tag)
    stem = f"{idx:02d}_{sanitize_title(title)[:48]}-{sanitize_title(author)[:20]}"
    raw_path = refs_dir / f"{stem}_raw.md"
    clean_path = refs_dir / f"{stem}_clean.md"
    raw_path.write_text(raw_text.strip() + "\n", encoding="utf-8")
    clean_path.write_text(clean_text(raw_text), encoding="utf-8")
    return raw_path, clean_path


def _fetch_wechat_article(url: str, refs_dir: Path, wechat_fetcher: Path, idx: int) -> str:
    tmp_dir = refs_dir / f"_tmp_fetch_{idx:02d}"
    ensure_dir(tmp_dir)
    cmd = ["npx", "-y", "bun", str(wechat_fetcher), url, "--output", str(tmp_dir)]
    cp = run(cmd)
    if cp.returncode != 0:
        raise RuntimeError(f"WeChat fetch failed: {cp.stderr.strip() or cp.stdout.strip()}")
    md_files = sorted(tmp_dir.glob("*.md"))
    if not md_files:
        raise RuntimeError("WeChat fetch produced no markdown file")
    return md_files[0].read_text(encoding="utf-8", errors="ignore")


def _build_video_placeholder(url: str) -> str:
    return (
        "# 视频来源占位（待手动补充）\n\n"
        f"来源链接：{url}\n\n"
        "自动抽取逐字稿失败。请把逐字稿粘贴到这个文件中，然后继续流程。\n\n"
        "建议结构：\n"
        "1. 原文逐字稿（可中英）\n"
        "2. 中文翻译稿\n"
        "3. 术语纠错后的最终稿\n"
    )


def _extract_json_tail(text: str) -> dict:
    raw = text.strip()
    if not raw:
        return {}
    pos = raw.rfind("\n{")
    if pos == -1 and raw.startswith("{"):
        pos = 0
    if pos == -1:
        return {}
    block = raw[pos:].strip()
    try:
        return json.loads(block)
    except Exception:
        return {}


def _vtt_to_text(vtt_text: str) -> str:
    rows: list[str] = []
    last = ""
    for raw in vtt_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("WEBVTT") or upper.startswith("NOTE ") or upper in {"STYLE", "REGION"}:
            continue
        if line.isdigit():
            continue
        if VTT_TIMECODE_RE.match(line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = html.unescape(line).strip()
        if not line:
            continue
        if line == last:
            continue
        rows.append(line)
        last = line
    return "\n".join(rows).strip()


def _fetch_youtube_transcript(url: str, refs_dir: Path, idx: int, runner: Path, download_script: Path) -> tuple[str, dict]:
    if not runner.exists() or not download_script.exists():
        raise FileNotFoundError("youtube-clipper scripts not found")

    tmp_dir = refs_dir / f"_tmp_yt_{idx:02d}"
    ensure_dir(tmp_dir)
    cmd = [str(runner), str(download_script), url, str(tmp_dir)]
    cp = run(cmd)
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.strip() or cp.stdout.strip() or "youtube-clipper download failed")

    payload = _extract_json_tail(cp.stdout)
    subtitle_path_raw = str(payload.get("subtitle_path") or "").strip()
    if not subtitle_path_raw:
        raise RuntimeError("youtube subtitle_path missing")

    subtitle_path = Path(subtitle_path_raw).expanduser().resolve()
    if not subtitle_path.exists():
        raise FileNotFoundError(f"subtitle file not found: {subtitle_path}")
    transcript = _vtt_to_text(subtitle_path.read_text(encoding="utf-8", errors="ignore"))
    if len(transcript) < 80:
        raise RuntimeError("subtitle transcript too short")

    title = str(payload.get("title") or "").strip()
    duration = payload.get("duration")
    header = ["# 来源", "", url, ""]
    if title:
        header.extend(["## 视频标题", "", title, ""])
    if duration:
        header.extend(["## 时长（秒）", "", str(duration), ""])
    header.extend(["## 逐字稿", "", transcript])
    return "\n".join(header).strip() + "\n", payload


def ingest_one(
    source: str,
    refs_dir: Path,
    wechat_fetcher: Path,
    youtube_runner: Path,
    youtube_download_script: Path,
    idx: int,
) -> dict:
    if is_url(source):
        domain = detect_domain(source)
        tag = slug_domain(source)
        # Prefer dedicated wechat fetcher for mp.weixin links.
        if domain == "mp.weixin.qq.com" and wechat_fetcher.exists():
            raw_text = _fetch_wechat_article(source, refs_dir, wechat_fetcher, idx)
            raw_path, clean_path = _write_pair(refs_dir, idx, tag, raw_text)
            return {
                "source": source,
                "kind": "url",
                "domain": domain,
                "status": "ok",
                "raw_path": str(raw_path),
                "clean_path": str(clean_path),
            }

        if domain in YOUTUBE_HOSTS and youtube_runner.exists() and youtube_download_script.exists():
            try:
                raw_text, payload = _fetch_youtube_transcript(
                    source, refs_dir, idx, youtube_runner, youtube_download_script
                )
                raw_path, clean_path = _write_pair(refs_dir, idx, tag, raw_text)
                return {
                    "source": source,
                    "kind": "video_url",
                    "domain": domain,
                    "status": "ok",
                    "extractor": "youtube-clipper",
                    "subtitle_path": str(payload.get("subtitle_path") or ""),
                    "raw_path": str(raw_path),
                    "clean_path": str(clean_path),
                }
            except Exception:
                # Fallback to generic/manual paths below.
                pass

        fetched = ""
        try:
            fetched = best_effort_fetch(source)
        except Exception:
            fetched = ""

        if is_video_url(source) and len(fetched) < 400:
            manual_path = refs_dir / f"{idx:02d}_{tag}_video_manual_input.md"
            manual_path.write_text(_build_video_placeholder(source), encoding="utf-8")
            raw_path, clean_path = _write_pair(refs_dir, idx, tag, f"来源：{source}\n\n请先补充逐字稿。")
            return {
                "source": source,
                "kind": "video_url",
                "domain": domain,
                "status": "manual_required",
                "manual_input_path": str(manual_path),
                "raw_path": str(raw_path),
                "clean_path": str(clean_path),
            }

        if not fetched:
            raise RuntimeError("Failed to fetch URL content")

        raw_text = f"# 来源\n\n{source}\n\n---\n\n{fetched}"
        raw_path, clean_path = _write_pair(refs_dir, idx, tag, raw_text)
        return {
            "source": source,
            "kind": "url",
            "domain": domain,
            "status": "ok",
            "raw_path": str(raw_path),
            "clean_path": str(clean_path),
        }

    path = Path(source).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Source file not found: {path}")
    tag = "local_file"
    raw_text = path.read_text(encoding="utf-8", errors="ignore")
    raw_path, clean_path = _write_pair(refs_dir, idx, tag, raw_text)
    return {
        "source": str(path),
        "kind": "file",
        "domain": "local",
        "status": "ok",
        "raw_path": str(raw_path),
        "clean_path": str(clean_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect sources into refs/ as raw+clean files")
    parser.add_argument("--topic-root", required=True, help="Topic root directory")
    parser.add_argument("--source", action="append", default=[], help="Source URL or local file path")
    parser.add_argument("--wechat-fetcher", default=str(DEFAULT_WECHAT_FETCHER))
    parser.add_argument("--youtube-runner", default=str(DEFAULT_YOUTUBE_RUNNER))
    parser.add_argument("--youtube-download-script", default=str(DEFAULT_YOUTUBE_DOWNLOAD_SCRIPT))
    args = parser.parse_args()

    topic_root = Path(args.topic_root).expanduser().resolve()
    refs_dir = ensure_dir(topic_root / "refs")
    wechat_fetcher = Path(args.wechat_fetcher).expanduser().resolve()
    youtube_runner = Path(args.youtube_runner).expanduser().resolve()
    youtube_download_script = Path(args.youtube_download_script).expanduser().resolve()

    if not args.source:
        raise ValueError("At least one --source is required")

    set_step(topic_root, "ingest_sources", RUNNING, message="Collecting source materials")

    results: list[dict] = []
    blocked = False
    try:
        idx = _next_index(refs_dir)
        for item in args.source:
            out = ingest_one(
                item,
                refs_dir,
                wechat_fetcher,
                youtube_runner,
                youtube_download_script,
                idx,
            )
            results.append(out)
            if out.get("status") == "manual_required":
                blocked = True
            idx += 1
    except Exception as exc:
        set_step(topic_root, "ingest_sources", FAILED, message=str(exc))
        raise

    report_path = topic_root / "meta" / "ingest_report.json"
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    set_artifact(topic_root, "ingest_report", str(report_path))
    total_refs = len(sorted(refs_dir.glob("*_clean.md")))
    set_artifact(topic_root, "refs_count", total_refs)

    if blocked:
        set_step(
            topic_root,
            "ingest_sources",
            BLOCKED,
            message="Some video sources require manual transcript input. Fill *_video_manual_input.md then rerun.",
            meta={"report": str(report_path)},
        )
        print(str(report_path))
        return 2

    set_step(topic_root, "ingest_sources", DONE, message="Source collection complete", meta={"report": str(report_path)})
    print(str(report_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
