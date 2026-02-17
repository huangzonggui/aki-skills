#!/usr/bin/env python3
"""
Publish local images as a WeChat Official Account draft via official APIs.

Flow:
1) Get stable access token
2) Upload cover image as permanent material (get thumb_media_id)
3) Upload all content images via uploadimg (get CDN URLs)
4) Build article HTML and call draft/add
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path
import random
import string
import sys
from typing import Dict, List, Optional
from urllib.parse import quote
from urllib.request import Request, urlopen


TOOLS_MD = Path.home() / ".openclaw" / "workspace" / "TOOLS.md"
WECHAT_CONFIG = Path.home() / ".config" / "wechat" / "config"

STABLE_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/stable_token"
UPLOAD_IMG_URL = "https://api.weixin.qq.com/cgi-bin/media/uploadimg"
ADD_MATERIAL_URL = "https://api.weixin.qq.com/cgi-bin/material/add_material"
DRAFT_ADD_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def read_kv_line(line: str) -> Optional[tuple[str, str]]:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export ") :].strip()
    if "=" not in line:
        return None
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if not key:
        return None
    return key, value


def load_credentials_from_files() -> None:
    # Priority: dedicated wechat config > legacy TOOLS.md
    for file_path in (WECHAT_CONFIG, TOOLS_MD):
        if not file_path.exists():
            continue
        for line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            parsed = read_kv_line(line)
            if not parsed:
                continue
            key, value = parsed
            if not value:
                continue
            if key in {"WECHAT_APP_ID", "WECHAT_ID", "APPID", "APP_ID"}:
                os.environ.setdefault("WECHAT_APP_ID", value)
                os.environ.setdefault("WECHAT_ID", value)
            elif key in {
                "WECHAT_APP_SECRET",
                "WECHAT_TOKEN",
                "APPSECRET",
                "APP_SECRET",
                "SECRET",
                "TOKEN",
            }:
                os.environ.setdefault("WECHAT_APP_SECRET", value)
                os.environ.setdefault("WECHAT_TOKEN", value)


def fail(message: str, details: Optional[Dict] = None, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    if details is not None:
        print(json.dumps(details, ensure_ascii=False, indent=2), file=sys.stderr)
    raise SystemExit(code)


def http_json(
    url: str,
    payload: Optional[Dict] = None,
    method: str = "POST",
    headers: Optional[Dict[str, str]] = None,
) -> Dict:
    body = None
    req_headers = {"User-Agent": "aki-wechat-api-imagepost/1.0"}
    if headers:
        req_headers.update(headers)

    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    req = Request(url=url, data=body, method=method, headers=req_headers)
    try:
        with urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as exc:
        fail(f"HTTP request failed: {url} ({exc})")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        fail(f"Response is not JSON: {url}", {"raw": raw[:800]})
    return {}


def multipart_file_upload(url: str, field_name: str, file_path: Path) -> Dict:
    boundary = "----CodexBoundary" + "".join(
        random.choice(string.ascii_letters + string.digits) for _ in range(24)
    )
    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

    file_bytes = file_path.read_bytes()
    preamble = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{file_path.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    ending = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = preamble + file_bytes + ending

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
        "User-Agent": "aki-wechat-api-imagepost/1.0",
    }
    req = Request(url=url, data=body, method="POST", headers=headers)
    try:
        with urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as exc:
        fail(f"Multipart upload failed: {url} ({exc})")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        fail(f"Upload response is not JSON: {url}", {"raw": raw[:800]})
    return {}


def ensure_wechat_ok(result: Dict, context: str) -> None:
    errcode = result.get("errcode")
    if errcode is not None and errcode != 0:
        fail(f"{context} failed", result)


def list_images(image_dir: Path) -> List[Path]:
    files = [
        p
        for p in image_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    return sorted(files, key=lambda p: p.name.lower())


def safe_title(title: str) -> str:
    trimmed = title.strip()
    if not trimmed:
        fail("title is empty")
    if len(trimmed) > 64:
        print("WARN: 标题超过 64 字，已自动截断。")
        trimmed = trimmed[:64]
    return trimmed


def safe_digest(digest: Optional[str]) -> str:
    if not digest:
        return ""
    d = digest.strip()
    if len(d) > 120:
        print("WARN: 摘要超过 120 字，已自动截断。")
        d = d[:120]
    return d


def html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def build_content_html(title: str, image_urls: List[str]) -> str:
    parts: List[str] = [f"<h1>{html_escape(title)}</h1>"]
    for idx, url in enumerate(image_urls, start=1):
        parts.append(
            f'<p><img src="{html_escape(url)}" alt="图{idx}" style="max-width:100%;" /></p>'
        )
    return "\n".join(parts)


def get_access_token(appid: str, secret: str, force_refresh: bool) -> str:
    payload = {
        "grant_type": "client_credential",
        "appid": appid,
        "secret": secret,
    }
    if force_refresh:
        payload["force_refresh"] = True
    result = http_json(STABLE_TOKEN_URL, payload, method="POST")
    ensure_wechat_ok(result, "get stable access token")
    token = result.get("access_token")
    if not token:
        fail("access_token missing in token response", result)
    return token


def upload_cover_for_thumb(access_token: str, cover_path: Path) -> str:
    url = f"{ADD_MATERIAL_URL}?access_token={quote(access_token)}&type=image"
    result = multipart_file_upload(url, "media", cover_path)
    ensure_wechat_ok(result, "upload cover image as permanent material")
    media_id = result.get("media_id")
    if not media_id:
        fail("thumb media_id missing in add_material response", result)
    return media_id


def upload_content_image(access_token: str, image_path: Path) -> str:
    url = f"{UPLOAD_IMG_URL}?access_token={quote(access_token)}"
    result = multipart_file_upload(url, "media", image_path)
    ensure_wechat_ok(result, f"upload content image ({image_path.name})")
    image_url = result.get("url")
    if not image_url:
        fail("url missing in uploadimg response", result)
    return image_url


def add_draft(
    access_token: str,
    *,
    title: str,
    author: str,
    digest: str,
    source_url: str,
    content_html: str,
    thumb_media_id: str,
) -> Dict:
    url = f"{DRAFT_ADD_URL}?access_token={quote(access_token)}"
    article = {
        "title": title,
        "author": author,
        "digest": digest,
        "content": content_html,
        "content_source_url": source_url,
        "thumb_media_id": thumb_media_id,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }
    result = http_json(url, {"articles": [article]}, method="POST")
    ensure_wechat_ok(result, "add draft")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish local images to WeChat Official Account draft via official APIs."
    )
    parser.add_argument("--dir", required=True, help="Image directory path")
    parser.add_argument("--title", required=True, help="Article title (<=64 chars)")
    parser.add_argument("--cover", help="Cover image path (default: first image)")
    parser.add_argument("--author", default="", help="Author name")
    parser.add_argument("--digest", default="", help="Article digest (<=120 chars)")
    parser.add_argument("--source-url", default="", help="Original source URL")
    parser.add_argument("--appid", help="WeChat AppID (override env)")
    parser.add_argument("--secret", help="WeChat AppSecret (override env)")
    parser.add_argument(
        "--force-refresh-token",
        action="store_true",
        help="Force refresh stable token",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_credentials_from_files()

    appid = args.appid or os.environ.get("WECHAT_APP_ID", "")
    secret = args.secret or os.environ.get("WECHAT_APP_SECRET", "")
    if not appid or not secret:
        fail(
            "Missing WECHAT_APP_ID / WECHAT_APP_SECRET. "
            "Set env vars, or add them to ~/.config/wechat/config "
            "(supports WECHAT_ID/WECHAT_TOKEN), or ~/.openclaw/workspace/TOOLS.md"
        )

    image_dir = Path(args.dir).expanduser().resolve()
    if not image_dir.exists() or not image_dir.is_dir():
        fail(f"Image directory not found: {image_dir}")

    images = list_images(image_dir)
    if not images:
        fail(f"No images found in directory: {image_dir}")

    cover_path = Path(args.cover).expanduser().resolve() if args.cover else images[0]
    if not cover_path.exists() or not cover_path.is_file():
        fail(f"Cover image not found: {cover_path}")

    title = safe_title(args.title)
    digest = safe_digest(args.digest)

    print(f"Image count: {len(images)}")
    print(f"Cover image: {cover_path}")
    print("Step 1/4: fetching stable token...")
    access_token = get_access_token(appid, secret, args.force_refresh_token)

    print("Step 2/4: uploading cover image for thumb_media_id...")
    thumb_media_id = upload_cover_for_thumb(access_token, cover_path)

    print("Step 3/4: uploading content images...")
    content_urls: List[str] = []
    for idx, image in enumerate(images, start=1):
        print(f"  - [{idx}/{len(images)}] {image.name}")
        content_urls.append(upload_content_image(access_token, image))

    print("Step 4/4: creating draft...")
    content_html = build_content_html(title, content_urls)
    result = add_draft(
        access_token,
        title=title,
        author=args.author.strip(),
        digest=digest,
        source_url=args.source_url.strip(),
        content_html=content_html,
        thumb_media_id=thumb_media_id,
    )

    media_id = result.get("media_id", "")
    print("SUCCESS: 草稿创建完成。")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if media_id:
        print(f"Draft media_id: {media_id}")


if __name__ == "__main__":
    main()
