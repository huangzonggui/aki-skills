#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from http.client import IncompleteRead
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
SHARED_DIR = REPO_ROOT / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from image_provider import (  # noqa: E402
    ImageProviderError,
    ImageRenderRequest,
    build_image_router,
    load_comfly_settings as shared_load_comfly_settings,
    render_image_with_provider as shared_render_image_with_provider,
    request_json as shared_request_json,
)


DEFAULT_IMAGE_API: dict[str, Any] = {
    "base_url": "https://ai.comfly.chat",
    "path": "/v1/images/generations",
    "api_key": "",
    "auth_header": "Authorization",
    "auth_prefix": "Bearer ",
    "response_format": "b64_json",
    "timeout_sec": 120,
    "aspect_ratio": "3:4",
    "image_size": "",
    "image": [],
    "accept_language": "zh-CN",
    "extra_body": {},
}
COMFLY_CONFIG_PATH = Path.home() / ".config" / "comfly" / "config"
KEYS_ENV_PATH = Path("/Users/aki/.config/ai/keys.env")

HEADING_RE = re.compile(r"^#{1,6}\s+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[\u3002\uff01\uff1f.!?])\s*")


def allowed_response_model_aliases(requested_model: str) -> set[str]:
    aliases: dict[str, set[str]] = {
        "nano-banana-pro": {"nano-banana-pro", "nano-banana-pro-4k", "nano-banana-2", "nano-banana-2-2k", "nano-banana-2-4k"},
        "nano-banana-pro-4k": {"nano-banana-pro-4k", "nano-banana-pro", "nano-banana-2-4k", "nano-banana-2-2k", "nano-banana-2"},
        "nano-banana-2": {"nano-banana-2", "nano-banana-2-2k", "nano-banana-2-4k", "nano-banana-pro", "nano-banana-pro-4k"},
        "nano-banana-2-2k": {"nano-banana-2-2k", "nano-banana-2", "nano-banana-2-4k", "nano-banana-pro", "nano-banana-pro-4k"},
        "nano-banana-2-4k": {"nano-banana-2-4k", "nano-banana-2-2k", "nano-banana-2", "nano-banana-pro-4k", "nano-banana-pro"},
    }
    return aliases.get(requested_model, {requested_model})


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def strip_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                return "\n".join(lines[idx + 1 :]).strip()
    return text.strip()


def extract_title(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return None


def split_sections(text: str) -> list[str]:
    lines = text.splitlines()
    sections: list[str] = []
    current: list[str] = []

    for line in lines:
        if HEADING_RE.match(line) and current:
            sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)

    if current:
        sections.append("\n".join(current).strip())

    return [s for s in sections if s.strip()]


def split_long_paragraph(paragraph: str, limit: int) -> list[str]:
    if len(paragraph) <= limit:
        return [paragraph]

    sentences = [s for s in SENTENCE_SPLIT_RE.split(paragraph) if s]
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if not current:
            if len(sentence) > limit:
                chunks.extend(sentence[i : i + limit] for i in range(0, len(sentence), limit))
            else:
                current = sentence
            continue

        if len(current) + len(sentence) > limit:
            chunks.append(current.strip())
            if len(sentence) > limit:
                chunks.extend(sentence[i : i + limit] for i in range(0, len(sentence), limit))
                current = ""
            else:
                current = sentence
        else:
            current += sentence

    if current:
        chunks.append(current.strip())

    return [c for c in chunks if c.strip()]


def split_section(section: str, max_chars: int) -> list[str]:
    if len(section) <= max_chars:
        return [section]

    lines = section.splitlines()
    header = lines[0].strip() if lines and HEADING_RE.match(lines[0]) else ""
    body = "\n".join(lines[1:]).strip() if header else section
    if not body:
        return [section[:max_chars]]

    limit = max_chars - len(header) - 1 if header else max_chars
    if limit < 200:
        limit = max_chars

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", body) if p.strip()]

    chunks: list[str] = []
    current = ""
    current_len = 0

    def push_current() -> None:
        nonlocal current
        if not current.strip():
            return
        if header:
            chunks.append(f"{header}\n{current.strip()}")
        else:
            chunks.append(current.strip())
        current = ""

    for paragraph in paragraphs:
        parts = split_long_paragraph(paragraph, limit)
        for part in parts:
            part_len = len(part)
            if current and current_len + part_len + 2 > limit:
                push_current()
                current = part
                current_len = part_len
            else:
                if current:
                    current += "\n\n" + part
                    current_len += part_len + 2
                else:
                    current = part
                    current_len = part_len

    if current:
        push_current()

    return chunks or [section[:max_chars]]


def chunk_article(text: str, max_chars: int) -> list[str]:
    sections = split_sections(text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for section in sections:
        for part in split_section(section, max_chars):
            part_len = len(part)
            if current and current_len + part_len > max_chars:
                chunks.append("\n\n".join(current).strip())
                current = [part]
                current_len = part_len
            else:
                current.append(part)
                current_len += part_len

    if current:
        chunks.append("\n\n".join(current).strip())

    return [c for c in chunks if c.strip()]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def summarize(text: str, limit: int = 140) -> str:
    single_line = re.sub(r"\s+", " ", text).strip()
    return single_line[:limit] + ("..." if len(single_line) > limit else "")


def write_outline(outline_path: Path, title: str | None, chunks: list[str]) -> None:
    lines = ["# Handnote Series Outline", ""]
    if title:
        lines.append(f"Title: {title}")
    lines.append(f"Images: {len(chunks)}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    width = max(2, len(str(len(chunks))))
    for idx, chunk in enumerate(chunks, start=1):
        label = str(idx).zfill(width)
        lines.append(f"## Image {label}")
        lines.append(f"Chars: {len(chunk)}")
        lines.append(f"Preview: {summarize(chunk)}")
        lines.append("")

    ensure_parent(outline_path)
    outline_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def build_prompt(
    constraints_text: str,
    style_text: str,
    title: str | None,
    page_label: str,
    chunk: str,
) -> str:
    parts = [constraints_text.strip(), style_text.strip()]
    if title:
        parts.append(f"Title: {title}")
    parts.append(f"Page: {page_label}")
    parts.append("Content:\n" + chunk.strip())
    return "\n\n".join(parts).strip() + "\n"


def merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def parse_env_like_file(path: Path) -> dict[str, str]:
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


def normalize_base_url(raw_url: str) -> str:
    url = raw_url.strip().rstrip("/")
    if not url:
        return ""
    suffixes = (
        "/v1/chat/completions",
        "/chat/completions",
        "/v1/images/generations",
        "/images/generations",
    )
    for suffix in suffixes:
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url


def normalize_image_bytes(raw: bytes) -> tuple[bytes, int]:
    if not raw:
        return raw, 0

    def is_webp_at(data: bytes, idx: int) -> bool:
        return idx + 12 <= len(data) and data[idx : idx + 4] == b"RIFF" and data[idx + 8 : idx + 12] == b"WEBP"

    signatures = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a")
    for sig in signatures:
        if raw.startswith(sig):
            return raw, 0
    if is_webp_at(raw, 0):
        return raw, 0

    candidates: list[int] = []
    for sig in signatures:
        idx = raw.find(sig)
        if idx > 0:
            candidates.append(idx)
    riff_idx = raw.find(b"RIFF")
    if riff_idx > 0 and is_webp_at(raw, riff_idx):
        candidates.append(riff_idx)

    if not candidates:
        return raw, 0
    strip_len = min(candidates)
    return raw[strip_len:], strip_len


def detect_image_format(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
        return "gif"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    return ""


def convert_with_sips(raw: bytes, src_format: str, dst_format: str) -> bytes | None:
    sips_bin = shutil.which("sips")
    if not sips_bin:
        return None

    src_ext = "jpeg" if src_format == "jpg" else src_format
    dst_ext = "jpeg" if dst_format == "jpg" else dst_format
    if not src_ext or not dst_ext:
        return None

    with tempfile.TemporaryDirectory(prefix="aki-dense-handnote-series-") as tmp_dir:
        src_path = Path(tmp_dir) / f"in.{src_ext}"
        dst_path = Path(tmp_dir) / f"out.{dst_ext}"
        src_path.write_bytes(raw)
        proc = subprocess.run(
            [sips_bin, "-s", "format", dst_ext, str(src_path), "--out", str(dst_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if proc.returncode != 0 or not dst_path.exists():
            return None
        return dst_path.read_bytes()


def load_image_api_settings(_skills_root: Path) -> dict[str, Any]:
    return shared_load_comfly_settings()


def request_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int) -> Any:
    try:
        return shared_request_json(url, headers, payload, timeout, provider="comfly")
    except ImageProviderError as exc:
        raise RuntimeError(str(exc)) from exc


def extract_first_image(payload: Any) -> tuple[str, str] | None:
    if not isinstance(payload, dict):
        return None

    data = payload.get("data") or payload.get("images") or payload.get("output")
    items: list[Any]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]
    else:
        items = []

    for item in items:
        if not isinstance(item, dict):
            continue
        if "b64_json" in item and isinstance(item["b64_json"], str):
            return "b64", item["b64_json"]
        if "base64" in item and isinstance(item["base64"], str):
            return "b64", item["base64"]
        if "url" in item and isinstance(item["url"], str):
            return "url", item["url"]
    return None


def download_image(url: str, timeout: int) -> bytes:
    req = Request(url, headers={"User-Agent": "aki-dense-handnote-series"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (URLError, TimeoutError) as exc:
        last_error = str(exc)
        for attempt in range(1, 4):
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                temp_path = Path(tmp.name)
            try:
                cp = subprocess.run(
                    [
                        "curl",
                        "--http1.1",
                        "-sSL",
                        "--retry",
                        "4",
                        "--retry-all-errors",
                        "--retry-delay",
                        "2",
                        "--max-time",
                        str(timeout),
                        "-H",
                        "User-Agent: aki-dense-handnote-series",
                        "-o",
                        str(temp_path),
                        url,
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if cp.returncode == 0:
                    return temp_path.read_bytes()
                last_error = cp.stderr.strip() or cp.stdout.strip() or last_error
                time.sleep(min(attempt, 3))
            finally:
                temp_path.unlink(missing_ok=True)
        raise RuntimeError(last_error) from exc


def generate_image_with_comfly(prompt: str, output_path: Path, settings: dict[str, Any]) -> None:
    shared_render_image_with_provider(prompt, output_path, "comfly", settings)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a dense handnote image series from a full article."
    )
    parser.add_argument("--article", required=True, help="Path to article markdown")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=1200,
        help="Max characters per image (default: 1200)",
    )
    parser.add_argument("--output-dir", help="Output directory for images")
    parser.add_argument("--prompt-only", action="store_true", help="Only write prompts")
    parser.add_argument("--title", help="Override title text")
    parser.add_argument("--session-id", help="Legacy option (ignored for Comfly API)")
    parser.add_argument("--model", help="Legacy option (ignored, model is locked)")
    parser.add_argument("--image-provider", choices=["auto", "comfly", "openrouter"], default="auto")
    args = parser.parse_args()

    article_path = Path(args.article).expanduser().resolve()
    if not article_path.exists():
        print(f"Article not found: {article_path}", file=sys.stderr)
        return 1

    skill_root = Path(__file__).resolve().parents[1]
    skills_root = skill_root.parent

    constraints_path = skill_root / "references" / "constraints.md"
    style_path = (
        skills_root
        / "aki-style-library"
        / "references"
        / "styles"
        / "手绘逻辑信息艺术设计师.md"
    )

    if not constraints_path.exists():
        print(f"Constraints not found: {constraints_path}", file=sys.stderr)
        return 1
    if not style_path.exists():
        print(f"Style template not found: {style_path}", file=sys.stderr)
        return 1

    article_text = strip_frontmatter(read_text(article_path))
    if not article_text:
        print("Article is empty.", file=sys.stderr)
        return 1

    title = args.title or extract_title(article_text)
    chunks = chunk_article(article_text, args.max_chars)
    if not chunks:
        print("No content chunks generated.", file=sys.stderr)
        return 1

    base_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else (
        article_path.parent / "imgs" / "handnote-series"
    )
    prompt_dir = base_dir / "prompts"
    outline_path = base_dir / "outline.md"

    constraints_text = read_text(constraints_path)
    style_text = read_text(style_path)

    width = max(2, len(str(len(chunks))))
    write_outline(outline_path, title, chunks)

    if args.session_id:
        print("Warning: --session-id is ignored when using Comfly API.")
    if args.model:
        print("Warning: --model is ignored; set COMFLY_IMAGE_MODEL in ~/.config/comfly/config.")

    requests: list[ImageRenderRequest] = []

    for idx, chunk in enumerate(chunks, start=1):
        label = str(idx).zfill(width)
        page_label = f"{idx}/{len(chunks)}"
        prompt_text = build_prompt(constraints_text, style_text, title, page_label, chunk)

        prompt_path = prompt_dir / f"{label}.md"
        output_path = base_dir / f"{label}.png"
        ensure_parent(prompt_path)
        prompt_path.write_text(prompt_text, encoding="utf-8")

        if args.prompt_only:
            continue
        requests.append(ImageRenderRequest(prompt=prompt_text, output_path=output_path))

    if requests:
        try:
            router = build_image_router(args.image_provider)
            batch_result = router.render_batch(requests)
        except (ImageProviderError, RuntimeError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        for item in batch_result.rendered_images:
            print(f"Image generated: {item.output_path}")

    print(f"Series complete: {base_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
