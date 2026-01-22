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

DEFAULT_CONFIG: Dict[str, Any] = {
    "image_api": {
        "token_url": "",
        "use_token_url": False,
        "base_url": "",
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


def env_or(value: str, env_key: str) -> str:
    env_val = os.environ.get(env_key, "").strip()
    return env_val or value


def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw in dotenv_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


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
    parser.add_argument("--config", default=None, help="Override workflow.config.json")
    parser.add_argument("--model", default=None, help="Override image model")
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

    dotenv_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path)

    root = Path(__file__).resolve().parents[1]
    config_path = Path(args.config).expanduser().resolve() if args.config else root / "workflow.config.json"
    config = load_config(config_path)
    settings = dict(config.get("image_api", {}))

    settings["api_key"] = env_or(settings.get("api_key", ""), "COMFLY_API_KEY")
    settings["base_url"] = env_or(settings.get("base_url", ""), "COMFLY_API_BASE_URL")
    settings["image_model"] = env_or(settings.get("image_model", ""), "COMFLY_IMAGE_MODEL")
    if args.model:
        settings["image_model"] = args.model
    if args.size:
        settings["size"] = args.size
    if args.n is not None:
        settings["n"] = args.n
    if args.response_format:
        settings["response_format"] = args.response_format

    if not settings.get("base_url"):
        raise SystemExit("Missing image_api.base_url (or COMFLY_API_BASE_URL).")
    if not settings.get("image_model"):
        raise SystemExit("Missing image_api.image_model (or COMFLY_IMAGE_MODEL).")
    if not settings.get("api_key"):
        raise SystemExit("Missing image_api.api_key (or COMFLY_API_KEY).")
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

    print(f"\n{'='*60}")
    print(f"Total: {len(prompt_blocks)} image(s) will be generated")
    print(f"Model: {settings['image_model']}")
    print(f"{'='*60}")

    if not args.confirm:
        print("\n🔴 DRY-RUN MODE - No API calls made.")
        print("Re-run with --confirm to generate images (THIS COSTS MONEY).")
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
        images = extract_images(response)
        if not images:
            raise SystemExit("No images returned by API.")

        label_slug = slugify(block["label"])
        item_record = {
            "label": block["label"],
            "prompt": block["prompt"],
            "negative_prompt": block["negative_prompt"],
            "response": redact_payload(response),
            "outputs": [],
        }

        for idx, image in enumerate(images, start=1):
            filename = f"{label_slug}-{idx}.png"
            if image["kind"] == "b64":
                data = base64.b64decode(image["data"])
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
