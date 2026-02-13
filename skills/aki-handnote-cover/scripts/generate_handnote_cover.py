#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOCKED_IMAGE_MODEL = "nano-banana-pro"
ALLOWED_RESPONSE_MODEL_ALIASES = {"nano-banana-2"}
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
    req = Request(url, headers={"User-Agent": "aki-handnote-cover"})
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
    if actual_model and actual_model != LOCKED_IMAGE_MODEL:
        if actual_model not in ALLOWED_RESPONSE_MODEL_ALIASES:
            raise RuntimeError(
                f"Model mismatch: requested '{LOCKED_IMAGE_MODEL}', got '{actual_model}'."
            )
        print(
            f"Warning: requested '{LOCKED_IMAGE_MODEL}', API returned alias '{actual_model}'."
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
        description="Generate a high-density handnote cover prompt from a full article."
    )
    parser.add_argument("--article", required=True, help="Path to article markdown")
    parser.add_argument("--output", help="Output image path (PNG). If omitted, uses timestamped filename")
    parser.add_argument("--prompt-out", help="Prompt markdown output path")
    parser.add_argument("--title", help="Override title text")
    parser.add_argument("--prompt-only", action="store_true", help="Only write prompt file")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing output image path",
    )
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

    article_text = read_text(article_path)
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

    parts = [read_text(constraints_path), read_text(style_path)]
    if title:
        parts.append(f"Title: {title}")
    parts.append("Article:\n" + article_text)
    prompt_text = "\n\n".join(parts).strip() + "\n"

    ensure_parent(prompt_out)
    prompt_out.write_text(prompt_text, encoding="utf-8")

    if args.prompt_only:
        print(f"Prompt written: {prompt_out}")
        return 0

    if args.session_id:
        print("Warning: --session-id is ignored when using Comfly API.")
    if args.model:
        print("Warning: --model is ignored; Comfly model is locked to nano-banana-pro.")

    try:
        settings = load_image_api_settings(skills_root)
        generate_image_with_comfly(prompt_text, output_path, settings)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Image generated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
