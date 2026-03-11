#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

RUDE_PHRASES = (
    "牛皮",
    "牛逼",
    "牛掰",
)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
PREFERRED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True)


def run_checked(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    cp = run(cmd, cwd=cwd)
    if cp.returncode != 0:
        raise RuntimeError(
            f"Command failed ({cp.returncode}): {' '.join(cmd)}\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
        )
    return cp


def sanitize_title(raw: str) -> str:
    text = re.sub(r"\s+", " ", raw.strip())
    text = re.sub(r"[\\/:*?\"<>|]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:80] or "untitled"


def find_min_prefix(base_dir: Path) -> int:
    nums: set[int] = set()
    for item in base_dir.iterdir():
        if not item.is_dir():
            continue
        m = re.match(r"^(\d+)\.\s*", item.name)
        if not m:
            continue
        nums.add(int(m.group(1)))
    candidate = 0
    while candidate in nums:
        candidate += 1
    return candidate


def ts_label() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M")


def detect_domain(raw: str) -> str:
    try:
        host = (urlparse(raw).hostname or "").strip().lower()
    except Exception:
        host = ""
    if not host:
        return "unknown"
    return host


def slug_domain(raw: str) -> str:
    d = detect_domain(raw)
    d = d.replace(".", "_")
    d = re.sub(r"[^a-z0-9_]+", "_", d)
    d = re.sub(r"_+", "_", d).strip("_")
    return d or "unknown"


def clean_text(raw: str) -> str:
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    first_h1 = ""
    prev = ""
    for line in lines:
        s = line.rstrip()
        for phrase in RUDE_PHRASES:
            s = s.replace(phrase, "")
        s = re.sub(r"[ \t]{2,}", " ", s).rstrip()
        stripped = s.strip()
        if not stripped:
            if out and out[-1] != "":
                out.append("")
            prev = ""
            continue
        if re.match(r"^\*\*作者\*\*[:：]", stripped):
            continue
        if re.match(r"^\*\*发布时间\*\*[:：]", stripped):
            continue
        if re.match(r"^\*\*原文链接\*\*[:：]", stripped):
            continue
        if stripped == "---":
            continue
        if "![ " in stripped or "![" in stripped:
            continue
        if re.match(r"^\s*(关注|点赞|在看|转发|点亮星标|写留言|一键三连|秒追)\s*$", stripped):
            continue
        if stripped.startswith("大家好，我是"):
            continue
        if "⑉" in stripped or "♡" in stripped:
            continue
        if re.match(r"^[\u4e00-\u9fffA-Za-z]+,?20\d{2}年\d{1,2}月\d{1,2}日", stripped):
            continue
        if re.match(r"^[A-Za-z0-9 .,:;+\-_/|()%\[\]\"']+$", stripped) and len(stripped) > 28:
            continue
        if re.match(r"^#\s+.+$", stripped):
            title = stripped[2:].strip()
            if not first_h1:
                first_h1 = title
                out.append(f"# {title}")
                prev = out[-1]
                continue
            if title == first_h1:
                continue
            out.append(stripped)
            prev = stripped
            continue
        if stripped == prev:
            continue
        out.append(s)
        prev = stripped
    cleaned = "\n".join(out)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() + "\n"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def copy_flattened_images(src_dirs: Iterable[Path], dst_dir: Path) -> list[Path]:
    ensure_dir(dst_dir)
    for old in dst_dir.glob("*"):
        if old.is_file():
            old.unlink()
    results: list[Path] = []
    idx = 1
    for src_dir in src_dirs:
        if not src_dir.exists():
            continue
        for image in sorted(src_dir.glob("*")):
            if not image.is_file():
                continue
            if image.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            dst = dst_dir / f"{idx:02d}{image.suffix.lower()}"
            shutil.copy2(image, dst)
            results.append(dst)
            idx += 1
    return results


def clear_directory(path: Path) -> None:
    if not path.exists():
        return
    for item in path.iterdir():
        if item.is_file() or item.is_symlink():
            item.unlink()
        else:
            shutil.rmtree(item)


def clear_image_files(path: Path) -> None:
    if not path.exists():
        return
    for file in path.rglob("*"):
        if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS:
            file.unlink()


def list_image_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(
        [file for file in path.iterdir() if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS],
        key=lambda item: item.name.lower(),
    )


def preferred_image_for_stem(directory: Path, stem: str) -> Path | None:
    for ext in PREFERRED_IMAGE_EXTENSIONS:
        candidate = directory / f"{stem}{ext}"
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def copy_selected_images(paths: Iterable[Path], dst_dir: Path) -> list[Path]:
    ensure_dir(dst_dir)
    clear_directory(dst_dir)
    copied: list[Path] = []
    for idx, src in enumerate(paths, start=1):
        suffix = src.suffix.lower() or ".png"
        dst = dst_dir / f"{idx:02d}{suffix}"
        shutil.copy2(src, dst)
        copied.append(dst)
    return copied


def convert_image_to_jpg(src: Path, dst: Path, quality: str = "90") -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "sips",
        "-s",
        "format",
        "jpeg",
        "-s",
        "formatOptions",
        quality,
        str(src),
        "--out",
        str(dst),
    ]
    run_checked(cmd)
    return dst


def load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json_file(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def is_url(text: str) -> bool:
    return text.startswith("http://") or text.startswith("https://")


def is_video_url(url: str) -> bool:
    host = detect_domain(url)
    video_hosts = {
        "youtube.com",
        "www.youtube.com",
        "youtu.be",
        "www.youtu.be",
        "vimeo.com",
        "www.vimeo.com",
        "bilibili.com",
        "www.bilibili.com",
        "douyin.com",
        "www.douyin.com",
        "xiaohongshu.com",
        "www.xiaohongshu.com",
        "channels.weixin.qq.com",
    }
    if host in video_hosts:
        return True
    return any(token in url.lower() for token in ("/video/", "watch?v=", ".mp4", ".mov"))


def merge_text_files(paths: list[Path]) -> str:
    chunks: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            continue
        chunks.append(f"# {path.name}\n\n{text}")
    return "\n\n".join(chunks).strip()


def best_effort_fetch(url: str, timeout: int = 25) -> str:
    import html
    import urllib.request

    req = urllib.request.Request(
        url=url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8", errors="ignore")
    data = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", data)
    data = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", data)
    data = re.sub(r"(?is)<[^>]+>", "\n", data)
    data = html.unescape(data)
    data = re.sub(r"\n{3,}", "\n\n", data)
    data = re.sub(r"[ \t]{2,}", " ", data)
    return data.strip()
