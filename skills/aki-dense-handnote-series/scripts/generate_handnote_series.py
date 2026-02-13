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
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


LOCKED_IMAGE_MODEL = "nano-banana-pro"
# Comfly may normalize/upgrade model id in the response payload.
# Keep request model locked, but accept compatible aliases when validating.
COMPATIBLE_RESPONSE_MODELS = {
    "nano-banana-pro",
    "nano-banana-2",
}
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

HEADING_RE = re.compile(r"^#{1,6}\s+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[\u3002\uff01\uff1f.!?])\s*")


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
    if not COMFLY_CONFIG_PATH.exists():
        raise RuntimeError(f"Missing Comfly config file: {COMFLY_CONFIG_PATH}")

    provider = parse_env_like_file(COMFLY_CONFIG_PATH)
    settings = dict(DEFAULT_IMAGE_API)
    settings["api_key"] = str(provider.get("COMFLY_API_KEY", "")).strip()
    settings["base_url"] = normalize_base_url(
        str(provider.get("COMFLY_API_BASE_URL") or provider.get("COMFLY_API_URL") or "")
    )
    settings["image_model"] = LOCKED_IMAGE_MODEL

    if not settings.get("base_url"):
        raise RuntimeError(
            f"Missing Comfly base URL. Set COMFLY_API_BASE_URL or COMFLY_API_URL in {COMFLY_CONFIG_PATH}."
        )
    if not settings.get("api_key"):
        raise RuntimeError(f"Missing Comfly API key. Set COMFLY_API_KEY in {COMFLY_CONFIG_PATH}.")
    return settings


def request_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int) -> Any:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Comfly API error {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Comfly API request failed: {exc}") from exc


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
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def generate_image_with_comfly(prompt: str, output_path: Path, settings: dict[str, Any]) -> None:
    path = str(settings.get("path") or "/v1/images/generations")
    if not path.startswith("/"):
        path = "/" + path
    api_url = str(settings["base_url"]).rstrip("/") + path

    headers = {
        "Content-Type": "application/json",
        str(settings.get("auth_header") or "Authorization"): (
            f"{str(settings.get('auth_prefix') or 'Bearer ')}{settings['api_key']}"
        ),
    }
    if settings.get("accept_language"):
        headers["Accept-Language"] = str(settings["accept_language"])

    payload: dict[str, Any] = {
        "model": LOCKED_IMAGE_MODEL,
        "prompt": prompt,
        "response_format": "b64_json",
    }
    if settings.get("aspect_ratio"):
        payload["aspect_ratio"] = settings["aspect_ratio"]
    if settings.get("image_size"):
        payload["image_size"] = settings["image_size"]
    if settings.get("image"):
        payload["image"] = settings["image"]

    extra_body = settings.get("extra_body") or {}
    if isinstance(extra_body, dict):
        payload.update(extra_body)

    timeout = int(settings.get("timeout_sec") or 120)
    response = request_json(api_url, headers, payload, timeout)

    actual_model = ""
    if isinstance(response, dict):
        model_val = response.get("model")
        if isinstance(model_val, str):
            actual_model = model_val.strip()
    if actual_model and actual_model not in COMPATIBLE_RESPONSE_MODELS:
        raise RuntimeError(
            f"Model mismatch: requested '{LOCKED_IMAGE_MODEL}', got '{actual_model}'."
        )

    image = extract_first_image(response)
    if not image:
        raise RuntimeError("No image data returned by Comfly API.")

    kind, data = image
    if kind == "b64":
        raw = base64.b64decode(data)
    else:
        raw = download_image(data, timeout)
    raw, stripped = normalize_image_bytes(raw)
    if stripped:
        print(
            f"Warning: stripped {stripped} unexpected leading bytes from image payload.",
            file=sys.stderr,
        )
    detected_format = detect_image_format(raw)
    output_ext = output_path.suffix.lower().lstrip(".")
    if output_ext == "jpeg":
        output_ext = "jpg"
    if detected_format and output_ext and detected_format != output_ext:
        converted = convert_with_sips(raw, detected_format, output_ext)
        if converted is not None:
            raw = converted
        else:
            print(
                f"Warning: output extension .{output_ext} mismatches returned {detected_format}; "
                "saved original bytes.",
                file=sys.stderr,
            )

    ensure_parent(output_path)
    output_path.write_bytes(raw)


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
        print("Warning: --model is ignored; Comfly request model is locked to nano-banana-pro.")

    settings: dict[str, Any] = {}
    if not args.prompt_only:
        try:
            settings = load_image_api_settings(skills_root)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1

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

        try:
            generate_image_with_comfly(prompt_text, output_path, settings)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        print(f"Image generated: {output_path}")

    print(f"Series complete: {base_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
