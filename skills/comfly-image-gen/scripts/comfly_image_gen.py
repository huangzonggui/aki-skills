#!/usr/bin/env python3
"""
Generate images from image_prompts.md via Comfly proxy API.

Defaults to dry-run; requires --confirm to execute paid API calls.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_SHARED_CONFIG_PATH = Path.home() / ".config" / "comfly" / "config"
DEFAULT_IMAGE_MODEL = "nano-banana-pro"

DEFAULT_CONFIG: Dict[str, Any] = {
    "image_api": {
        "token_url": "",
        "use_token_url": False,
        "base_url": "https://ai.comfly.chat",
        "path": "/v1/images/generations",
        "api_key": "",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "image_model": "",
        "size": "1024x1024",
        "n": 1,
        "response_format": "b64_json",
        "timeout_sec": 120,
        "negative_prompt_field": "",
        "aspect_ratio": "",
        "image_size": "",
        "image": [],
        "accept_language": "",
        "extra_body": {},
        "request_template": {},
    }
}
def merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return DEFAULT_CONFIG
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in config: {path}\n{exc}") from exc
    return merge_dicts(DEFAULT_CONFIG, data)


def load_env_file(path: Path, overwrite_existing: bool = False) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if not overwrite_existing and key in os.environ:
            continue
        os.environ[key] = value.strip().strip("'\"")


def normalize_base_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""

    for suffix in ("/v1/chat/completions", "/v1/images/generations"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
            break

    return raw.rstrip("/")


def normalize_image_bytes(raw: bytes) -> Tuple[bytes, int]:
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

    candidates: List[int] = []
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


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return cleaned or "image"


def normalize_text(lines: List[str]) -> str:
    joined = " ".join(line.strip(" -*") for line in lines if line.strip())
    return re.sub(r"\s+", " ", joined).strip()


def split_prompt_lines(lines: List[str]) -> Tuple[str, str]:
    positive: List[str] = []
    negative: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"(?i)^negative( prompt)?\s*:", stripped):
            negative.append(stripped.split(":", 1)[1].strip())
        else:
            positive.append(stripped)
    return normalize_text(positive), normalize_text(negative)


def parse_prompt_blocks(text: str) -> List[Dict[str, str]]:
    blocks: List[Dict[str, str]] = []
    current_label: Optional[str] = None
    current_lines: List[str] = []

    def commit_block() -> None:
        nonlocal current_label, current_lines
        if current_label and current_lines:
            prompt, negative = split_prompt_lines(current_lines)
            if prompt:
                blocks.append(
                    {"label": current_label, "prompt": prompt, "negative_prompt": negative}
                )
        current_label = None
        current_lines = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if current_lines:
                current_lines.append("")
            continue
        label = None
        if line.startswith("#"):
            label = line.lstrip("#").strip()
        else:
            trimmed = line.rstrip(":")
            if re.match(r"^(Cover|Infographic|Figure|Image)\b", trimmed, re.IGNORECASE):
                if len(trimmed.split()) <= 3:
                    label = trimmed
        if label:
            commit_block()
            current_label = label
            continue
        current_lines.append(line)

    if current_label:
        commit_block()

    if not blocks:
        prompt, negative = split_prompt_lines([l for l in text.splitlines() if l.strip()])
        if prompt:
            blocks.append({"label": "Image", "prompt": prompt, "negative_prompt": negative})
    return blocks


def render_template(template: Any, mapping: Dict[str, Any]) -> Any:
    if isinstance(template, dict):
        return {k: render_template(v, mapping) for k, v in template.items()}
    if isinstance(template, list):
        return [render_template(item, mapping) for item in template]
    if isinstance(template, str):
        token = re.fullmatch(r"{(\w+)}", template)
        if token:
            key = token.group(1)
            if key in mapping:
                return mapping[key]
        try:
            return template.format_map(mapping)
        except KeyError:
            return template
    return template


def prune_empty(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            item_clean = prune_empty(item)
            if item_clean is None:
                continue
            if isinstance(item_clean, str) and item_clean.strip() == "":
                continue
            if isinstance(item_clean, (list, dict)) and not item_clean:
                continue
            cleaned[key] = item_clean
        return cleaned
    if isinstance(value, list):
        cleaned_list = []
        for item in value:
            item_clean = prune_empty(item)
            if item_clean is None:
                continue
            if isinstance(item_clean, str) and item_clean.strip() == "":
                continue
            if isinstance(item_clean, (list, dict)) and not item_clean:
                continue
            cleaned_list.append(item_clean)
        return cleaned_list
    return value


def build_request_body(
    settings: Dict[str, Any], prompt: str, negative_prompt: str
) -> Dict[str, Any]:
    mapping = {
        "model": settings["image_model"],
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "size": settings["size"],
        "n": settings["n"],
        "response_format": settings["response_format"],
        "aspect_ratio": settings.get("aspect_ratio", ""),
        "image_size": settings.get("image_size", ""),
        "image": settings.get("image", []),
    }
    template = settings.get("request_template") or {}
    if template:
        return prune_empty(render_template(template, mapping))

    body: Dict[str, Any] = {
        "model": settings["image_model"],
        "prompt": prompt,
    }
    if settings.get("size"):
        body["size"] = settings["size"]
    if settings.get("n") is not None:
        body["n"] = settings["n"]
    if settings.get("response_format"):
        body["response_format"] = settings["response_format"]
    negative_field = settings.get("negative_prompt_field") or ""
    if negative_field and negative_prompt:
        body[negative_field] = negative_prompt
    if settings.get("aspect_ratio"):
        body["aspect_ratio"] = settings["aspect_ratio"]
    if settings.get("image_size"):
        body["image_size"] = settings["image_size"]
    if settings.get("image"):
        body["image"] = settings["image"]
    extra_body = settings.get("extra_body") or {}
    if isinstance(extra_body, dict):
        body.update(extra_body)
    return body


def request_json(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int) -> Any:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"API error {exc.code}: {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"API request failed: {exc}") from exc


def extract_images(payload: Any) -> List[Dict[str, str]]:
    images: List[Dict[str, str]] = []
    if isinstance(payload, dict):
        data = payload.get("data") or payload.get("images") or payload.get("output")
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                if "b64_json" in item:
                    images.append({"kind": "b64", "data": item["b64_json"]})
                elif "base64" in item:
                    images.append({"kind": "b64", "data": item["base64"]})
                elif "url" in item:
                    images.append({"kind": "url", "data": item["url"]})
        elif isinstance(data, dict):
            if "b64_json" in data:
                images.append({"kind": "b64", "data": data["b64_json"]})
            elif "base64" in data:
                images.append({"kind": "b64", "data": data["base64"]})
            elif "url" in data:
                images.append({"kind": "url", "data": data["url"]})
    return images


def redact_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        scrubbed = {}
        for key, value in payload.items():
            if key in {"b64_json", "base64"}:
                scrubbed[key] = f"<redacted:{len(value)}>"
            else:
                scrubbed[key] = redact_payload(value)
        return scrubbed
    if isinstance(payload, list):
        return [redact_payload(item) for item in payload]
    return payload


def download_image(url: str, timeout: int) -> Tuple[bytes, str]:
    req = Request(url, headers={"User-Agent": "comfly-image-gen"})
    with urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get("Content-Type", "")
        data = resp.read()
    ext = "png"
    if "jpeg" in content_type or "jpg" in content_type:
        ext = "jpg"
    elif "webp" in content_type:
        ext = "webp"
    return data, ext


def ensure_can_write(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"Refusing to overwrite existing path: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate images via Comfly API")
    parser.add_argument("--topic", required=True, help="Path to the topic folder")
    parser.add_argument("--prompts", default=None, help="Path to image_prompts.md")
    parser.add_argument("--out", default=None, help="Output directory for images")
    parser.add_argument("--meta", default=None, help="Metadata output JSON path")
    parser.add_argument("--config", default=None, help="Optional JSON override file (expects image_api object)")
    parser.add_argument("--size", default=None, help="Override image size")
    parser.add_argument("--n", type=int, default=None, help="Images per prompt")
    parser.add_argument("--response-format", default=None, help="Override response format")
    parser.add_argument("--confirm", action="store_true", help="Actually call the API")
    parser.add_argument("--force", action="store_true", help="Overwrite existing outputs")
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Do not download URLs; only record them in metadata",
    )
    args = parser.parse_args()

    shared_config_path = Path(
        os.environ.get("COMFLY_SHARED_CONFIG_PATH", str(DEFAULT_SHARED_CONFIG_PATH))
    ).expanduser()
    # Unified shared config is the single source of truth.
    load_env_file(shared_config_path)
    config: Dict[str, Any] = DEFAULT_CONFIG
    if args.config:
        config_path = Path(args.config).expanduser().resolve()
        if not config_path.exists():
            raise SystemExit(f"Config file not found: {config_path}")
        config = load_config(config_path)
    settings = dict(config.get("image_api", {}))

    settings["api_key"] = str(
        os.environ.get("COMFLY_API_KEY", settings.get("api_key", ""))
    ).strip()

    env_base_url = str(os.environ.get("COMFLY_API_BASE_URL", "")).strip()
    env_api_url = str(os.environ.get("COMFLY_API_URL", "")).strip()
    cfg_base_url = str(settings.get("base_url", "")).strip()
    settings["base_url"] = normalize_base_url(env_base_url or env_api_url or cfg_base_url)

    env_image_model = str(os.environ.get("COMFLY_IMAGE_MODEL", "")).strip()
    env_model_alias = str(
        os.environ.get("COMFLY_MODEL", os.environ.get("COMFLY_CHAT_MODEL", ""))
    ).strip()
    cfg_image_model = str(settings.get("image_model", "")).strip()
    resolved_model = env_image_model or cfg_image_model or env_model_alias or DEFAULT_IMAGE_MODEL
    settings["image_model"] = resolved_model

    settings["path"] = str(os.environ.get("COMFLY_IMAGE_PATH", settings.get("path", "/v1/images/generations"))).strip()
    if args.size:
        settings["size"] = args.size
    if args.n is not None:
        settings["n"] = args.n
    if args.response_format:
        settings["response_format"] = args.response_format

    if not settings.get("base_url"):
        raise SystemExit(
            "Missing base URL. Set COMFLY_API_BASE_URL (or COMFLY_API_URL) in "
            f"{shared_config_path}."
        )
    if not settings.get("api_key"):
        raise SystemExit(
            "Missing API key. Set COMFLY_API_KEY in "
            f"{shared_config_path}."
        )
    if not settings.get("image_model"):
        raise SystemExit(
            "Missing image model. Set COMFLY_IMAGE_MODEL in "
            f"{shared_config_path}."
        )
    if settings.get("use_token_url"):
        raise SystemExit(
            "Token exchange is not implemented yet; set image_api.use_token_url to false."
        )

    topic_dir = Path(args.topic).expanduser().resolve()
    if not topic_dir.exists():
        raise SystemExit(f"Topic folder not found: {topic_dir}")

    prompts_path = Path(args.prompts).expanduser().resolve() if args.prompts else topic_dir / "outputs" / "image_prompts.md"
    if not prompts_path.exists():
        raise SystemExit(f"Prompts file not found: {prompts_path}")

    out_dir = Path(args.out).expanduser().resolve() if args.out else topic_dir / "outputs" / "images"
    meta_path = Path(args.meta).expanduser().resolve() if args.meta else topic_dir / "outputs" / "image_generations.json"

    prompts_text = prompts_path.read_text(encoding="utf-8", errors="ignore")
    prompt_blocks = parse_prompt_blocks(prompts_text)
    if not prompt_blocks:
        raise SystemExit("No prompts found in image_prompts.md.")

    print("Planned image generations:")
    for block in prompt_blocks:
        snippet = block["prompt"][:120] + ("..." if len(block["prompt"]) > 120 else "")
        print(f"- {block['label']}: {snippet}")
    print(f"Image model: {settings['image_model']}")

    if not args.confirm:
        print("\nDry-run only. Re-run with --confirm to generate images.")
        return

    ensure_can_write(out_dir, args.force)
    ensure_can_write(meta_path, args.force)

    out_dir.mkdir(parents=True, exist_ok=True)

    path = settings.get("path", "/v1/images/generations") or "/v1/images/generations"
    if not path.startswith("/"):
        path = "/" + path
    api_url = settings["base_url"].rstrip("/") + path
    headers = {
        "Content-Type": "application/json",
        settings.get("auth_header", "Authorization"): f"{settings.get('auth_prefix', 'Bearer ')}{settings['api_key']}",
    }
    if settings.get("accept_language"):
        headers["Accept-Language"] = str(settings["accept_language"])

    metadata: Dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "api_url": api_url,
        "model": settings["image_model"],
        "items": [],
    }

    timeout = int(settings.get("timeout_sec") or 120)
    download_urls = not args.no_download

    for block in prompt_blocks:
        payload = build_request_body(settings, block["prompt"], block["negative_prompt"])
        response = request_json(api_url, headers, payload, timeout)
        actual_model = ""
        if isinstance(response, dict):
            model_val = response.get("model")
            if isinstance(model_val, str):
                actual_model = model_val.strip()
        if actual_model and actual_model != settings["image_model"]:
            print(
                f"Warning: requested '{settings['image_model']}', API returned '{actual_model}'.",
                file=sys.stderr,
            )
        images = extract_images(response)
        if not images:
            raise SystemExit("No images returned by API.")

        label_slug = slugify(block["label"])
        item_record = {
            "label": block["label"],
            "prompt": block["prompt"],
            "negative_prompt": block["negative_prompt"],
            "requested_model": settings["image_model"],
            "response_model": actual_model,
            "response": redact_payload(response),
            "outputs": [],
        }

        for idx, image in enumerate(images, start=1):
            filename = f"{label_slug}-{idx}.png"
            if image["kind"] == "b64":
                data = base64.b64decode(image["data"])
                data, stripped = normalize_image_bytes(data)
                if stripped:
                    print(
                        f"Warning: stripped {stripped} unexpected leading bytes from image payload.",
                        file=sys.stderr,
                    )
                ext = detect_image_format(data) or "png"
                filename = f"{label_slug}-{idx}.{ext}"
                (out_dir / filename).write_bytes(data)
                item_record["outputs"].append(str(out_dir / filename))
            elif image["kind"] == "url":
                if download_urls:
                    data, ext = download_image(image["data"], timeout)
                    filename = f"{label_slug}-{idx}.{ext}"
                    (out_dir / filename).write_bytes(data)
                    item_record["outputs"].append(str(out_dir / filename))
                else:
                    item_record["outputs"].append(image["data"])

        metadata["items"].append(item_record)

    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved images to: {out_dir}")
    print(f"Metadata: {meta_path}")


if __name__ == "__main__":
    main()
