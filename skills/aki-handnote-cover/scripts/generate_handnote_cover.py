#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cover_prompt_builder import (
    COVER_CONSTRAINTS_PATH,
    STYLE_TEMPLATE_PATH,
    build_handnote_cover_prompt,
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


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def extract_title(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return None


META_LINE_RE = re.compile(r"^\*\*(作者|发布时间|原文链接)\*\*:\s*", re.IGNORECASE)
HEADING_IMAGE_RE = re.compile(r"^#{1,6}\s*!\[[^\]]*\]\([^)]+\)\)*\s*$")
IMAGE_PLACEHOLDER_RE = re.compile(r"^!\[(图片|Image\s*\d+)\]\((640|[^)]+)\)\)*\s*$", re.IGNORECASE)
URL_ONLY_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
RATIO_LINE_RE = re.compile(r"^\d+\s*/\s*\d+$")
STAR_ONLY_RE = re.compile(r"^\*{2,}\s*$")
REFERENCE_RE = re.compile(r"^参考资料[：:]?\s*$")
NOISE_KEYWORDS = (
    "已关注",
    "关注",
    "点赞",
    "在看",
    "转发",
    "一键三连",
    "点亮星标",
    "锁定",
    "秒追",
    "观看更多",
    "退出全屏",
    "切换到竖屏",
    "切换到横屏",
    "倍速",
    "重播",
    "写下你的评论",
    "已同步到看一看",
    "您的浏览器不支持 video 标签",
    "视频详情",
)


def _looks_like_noise_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if META_LINE_RE.search(s):
        return True
    if HEADING_IMAGE_RE.match(s):
        return True
    if IMAGE_PLACEHOLDER_RE.match(s):
        return True
    if STAR_ONLY_RE.match(s):
        return True
    if RATIO_LINE_RE.match(s):
        return True
    if "00:00/" in s or "继续播放进度条" in s:
        return True
    if any(keyword in s for keyword in NOISE_KEYWORDS):
        return True
    return False


def clean_article_for_cover(raw_text: str) -> str:
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")

    # Drop metadata preamble between title and first horizontal rule.
    first_hr = next((i for i, line in enumerate(lines[:60]) if line.strip() == "---"), -1)
    if first_hr > 0:
        head = lines[:first_hr]
        if any(META_LINE_RE.search(line.strip()) for line in head):
            if lines[0].strip().startswith("# "):
                lines = [lines[0]] + lines[first_hr + 1 :]
            else:
                lines = lines[first_hr + 1 :]

    cleaned: list[str] = []
    title_text = ""
    for line in lines:
        s = line.strip()
        if s.startswith("# "):
            title_text = s[2:].strip()
            break

    title_seen = False
    in_reference_tail = False
    for raw in lines:
        line = raw.replace("\u00a0", " ").strip()
        if line.startswith("# "):
            title_seen = True
            cleaned.append(line)
            continue

        if title_text and title_seen and line == title_text:
            continue

        if REFERENCE_RE.match(line):
            in_reference_tail = True
            continue

        if in_reference_tail:
            # In WeChat posts, this tail is usually URL + CTA noise.
            if not line or URL_ONLY_RE.match(line) or _looks_like_noise_line(line):
                continue
            # Only resume when a substantial non-noise sentence appears.
            if len(line) >= 16 and not _looks_like_noise_line(line):
                in_reference_tail = False
            else:
                continue

        if _looks_like_noise_line(line):
            continue
        cleaned.append(line)

    compact: list[str] = []
    last_blank = False
    for line in cleaned:
        blank = line == ""
        if blank and last_blank:
            continue
        compact.append(line)
        last_blank = blank

    result = "\n".join(compact).strip()
    if len(result) < max(200, len(normalized.strip()) // 5):
        return raw_text.strip()
    return result


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def pick_non_overwriting_path(path: Path) -> Path:
    if not path.exists():
        return path
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.stem}.{ts}{path.suffix}")
    if not candidate.exists():
        return candidate
    idx = 2
    while True:
        candidate = path.with_name(f"{path.stem}.{ts}.{idx}{path.suffix}")
        if not candidate.exists():
            return candidate
        idx += 1


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


def allowed_response_model_aliases(requested_model: str) -> set[str]:
    aliases: dict[str, set[str]] = {
        "nano-banana-pro": {"nano-banana-2"},
        "gemini-3.1-flash-image-preview": {"nano-banana-2"},
    }
    return aliases.get(requested_model, set())


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


def decode_base64_image_payload(data: str) -> bytes:
    payload = data.strip()
    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1]
    payload = re.sub(r"\s+", "", payload)
    payload = payload.replace("-", "+").replace("_", "/")
    payload = re.sub(r"[^A-Za-z0-9+/=]", "", payload)
    if not payload:
        raise RuntimeError("Empty base64 image payload.")

    padding = (-len(payload)) % 4
    if padding:
        payload += "=" * padding
    try:
        return base64.b64decode(payload, validate=False)
    except Exception as exc:
        raise RuntimeError(f"Failed to decode base64 image payload: {exc}") from exc


def convert_with_sips(raw: bytes, src_format: str, dst_format: str) -> bytes | None:
    sips_bin = shutil.which("sips")
    if not sips_bin:
        return None

    src_ext = "jpeg" if src_format == "jpg" else src_format
    dst_ext = "jpeg" if dst_format == "jpg" else dst_format
    if not src_ext or not dst_ext:
        return None

    with tempfile.TemporaryDirectory(prefix="aki-handnote-cover-") as tmp_dir:
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
    settings["image_model"] = str(provider.get("COMFLY_IMAGE_MODEL", "")).strip()

    if not settings.get("base_url"):
        raise RuntimeError(
            f"Missing Comfly base URL. Set COMFLY_API_BASE_URL or COMFLY_API_URL in {COMFLY_CONFIG_PATH}."
        )
    if not settings.get("api_key"):
        raise RuntimeError(f"Missing Comfly API key. Set COMFLY_API_KEY in {COMFLY_CONFIG_PATH}.")
    if not settings.get("image_model"):
        raise RuntimeError(
            f"Missing image model. Set COMFLY_IMAGE_MODEL in {COMFLY_CONFIG_PATH}."
        )
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
    req = Request(url, headers={"User-Agent": "aki-handnote-cover"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def build_comfly_request(
    prompt: str, settings: dict[str, Any]
) -> tuple[str, dict[str, str], dict[str, Any], int, str]:
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

    requested_model = str(settings.get("image_model") or DEFAULT_IMAGE_MODEL).strip()
    payload: dict[str, Any] = {
        "model": requested_model,
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
    return api_url, headers, payload, timeout, requested_model


def mask_sensitive_headers(headers: dict[str, str]) -> dict[str, str]:
    masked: dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in {"authorization", "x-api-key", "api-key"}:
            masked[key] = "***masked***"
        else:
            masked[key] = value
    return masked


def dump_comfly_payload(
    dump_path: Path,
    *,
    article_path: Path,
    prompt_path: Path,
    api_url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: int,
) -> None:
    prompt_text = str(payload.get("prompt", ""))
    dump = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "article_path": str(article_path),
        "prompt_path": str(prompt_path),
        "api_url": api_url,
        "timeout_sec": timeout,
        "headers": mask_sensitive_headers(headers),
        "payload": payload,
        "prompt_stats": {
            "chars": len(prompt_text),
            "bytes": len(prompt_text.encode("utf-8")),
            "sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
            "head": prompt_text[:220],
            "tail": prompt_text[-220:],
        },
    }
    ensure_parent(dump_path)
    dump_path.write_text(json.dumps(dump, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate_image_with_comfly(prompt: str, output_path: Path, settings: dict[str, Any]) -> None:
    api_url, headers, payload, timeout, requested_model = build_comfly_request(prompt, settings)
    response = request_json(api_url, headers, payload, timeout)

    actual_model = ""
    if isinstance(response, dict):
        model_val = response.get("model")
        if isinstance(model_val, str):
            actual_model = model_val.strip()
    if actual_model and actual_model != requested_model:
        if actual_model not in allowed_response_model_aliases(requested_model):
            raise RuntimeError(
                f"Model mismatch: requested '{requested_model}', got '{actual_model}'."
            )
        print(
            f"Warning: requested '{requested_model}', API returned alias '{actual_model}'."
        )

    image = extract_first_image(response)
    if not image:
        raise RuntimeError("No image data returned by Comfly API.")

    kind, data = image
    if kind == "b64":
        raw = decode_base64_image_payload(data)
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
        description="Generate a high-density handnote cover prompt from a full article."
    )
    parser.add_argument("--article", required=True, help="Path to article markdown")
    parser.add_argument("--output", help="Output image path (PNG). If omitted, uses timestamped filename")
    parser.add_argument("--prompt-out", help="Prompt markdown output path")
    parser.add_argument("--title", help="Override title text")
    parser.add_argument("--prompt-only", action="store_true", help="Only write prompt file")
    parser.add_argument(
        "--raw-article",
        action="store_true",
        help="Use raw article text without cleanup (default: cleaned for cover generation)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing output image path",
    )
    parser.add_argument("--dump-payload", help="Write Comfly request payload JSON to this path")
    parser.add_argument(
        "--dump-only",
        action="store_true",
        help="Only dump payload and exit (no API image generation)",
    )
    parser.add_argument("--session-id", help="Legacy option (ignored for Comfly API)")
    parser.add_argument("--model", help="Legacy option (ignored, use COMFLY_IMAGE_MODEL)")
    args = parser.parse_args()

    article_path = Path(args.article).expanduser().resolve()
    if not article_path.exists():
        print(f"Article not found: {article_path}", file=sys.stderr)
        return 1

    skill_root = Path(__file__).resolve().parents[1]
    skills_root = skill_root.parent

    constraints_path = COVER_CONSTRAINTS_PATH
    style_path = STYLE_TEMPLATE_PATH

    if not constraints_path.exists():
        print(f"Constraints not found: {constraints_path}", file=sys.stderr)
        return 1
    if not style_path.exists():
        print(f"Style template not found: {style_path}", file=sys.stderr)
        return 1

    raw_article_text = read_text(article_path)
    article_text = raw_article_text if args.raw_article else clean_article_for_cover(raw_article_text)
    title = args.title or extract_title(article_text)

    base_dir = article_path.parent
    prompt_out = Path(args.prompt_out).expanduser().resolve() if args.prompt_out else (
        base_dir / "imgs" / "prompts" / "handnote-cover.md"
    )
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = base_dir / "imgs" / f"handnote-cover.{ts}.png"

    if args.output and not args.overwrite:
        safe_output_path = pick_non_overwriting_path(output_path)
        if safe_output_path != output_path:
            print(f"Output exists, writing new file instead: {safe_output_path}")
        output_path = safe_output_path

    prompt_text = build_handnote_cover_prompt(
        article_text,
        title or "",
        constraints_text=read_text(constraints_path),
        style_text=read_text(style_path),
    )

    ensure_parent(prompt_out)
    prompt_out.write_text(prompt_text, encoding="utf-8")

    if args.prompt_only:
        print(f"Prompt written: {prompt_out}")
        return 0

    if args.session_id:
        print("Warning: --session-id is ignored for Comfly API.")
    if args.model:
        print("Warning: --model is ignored; set COMFLY_IMAGE_MODEL in ~/.config/comfly/config.")

    try:
        settings = load_image_api_settings(skills_root)
        if args.dump_payload:
            dump_path = Path(args.dump_payload).expanduser().resolve()
            api_url, headers, payload, timeout, _ = build_comfly_request(prompt_text, settings)
            dump_comfly_payload(
                dump_path,
                article_path=article_path,
                prompt_path=prompt_out,
                api_url=api_url,
                headers=headers,
                payload=payload,
                timeout=timeout,
            )
            print(f"Payload dumped: {dump_path}")
            if args.dump_only:
                return 0
        generate_image_with_comfly(prompt_text, output_path, settings)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Image generated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
