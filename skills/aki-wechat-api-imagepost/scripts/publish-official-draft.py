#!/usr/bin/env python3
"""
Publish WeChat Official Account drafts via official APIs.

Supported modes:
1) imagepost: publish a local image directory as an image-text draft
2) article: publish from markdown/html/html-content as an article draft

Official API chain:
1. POST /cgi-bin/stable_token
2. POST /cgi-bin/material/add_material?type=image (cover -> thumb_media_id)
3. POST /cgi-bin/media/uploadimg (content image URLs)
4. POST /cgi-bin/draft/add
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path
import random
import re
import string
import sys
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, unquote
from urllib.request import Request, urlopen


TOOLS_MD = Path.home() / ".openclaw" / "workspace" / "TOOLS.md"
WECHAT_CONFIG = Path.home() / ".config" / "wechat" / "config"

STABLE_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/stable_token"
UPLOAD_IMG_URL = "https://api.weixin.qq.com/cgi-bin/media/uploadimg"
ADD_MATERIAL_URL = "https://api.weixin.qq.com/cgi-bin/material/add_material"
DRAFT_ADD_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def read_kv_line(line: str) -> Optional[Tuple[str, str]]:
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


def ensure_exists_file(path: Path, label: str) -> None:
    if not path.exists() or not path.is_file():
        fail(f"{label} not found: {path}")


def is_remote_or_data_url(src: str) -> bool:
    s = src.strip().lower()
    return (
        s.startswith("http://")
        or s.startswith("https://")
        or s.startswith("data:")
        or s.startswith("//")
    )


def strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


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


def upload_content_image(
    access_token: str, image_path: Path, cache: Dict[str, str]
) -> str:
    key = str(image_path.resolve())
    if key in cache:
        return cache[key]
    url = f"{UPLOAD_IMG_URL}?access_token={quote(access_token)}"
    result = multipart_file_upload(url, "media", image_path)
    ensure_wechat_ok(result, f"upload content image ({image_path.name})")
    image_url = result.get("url")
    if not image_url:
        fail("url missing in uploadimg response", result)
    cache[key] = image_url
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


def resolve_local_path(raw_src: str, base_dir: Path) -> Optional[Path]:
    src = raw_src.strip().strip("<>").strip()
    if not src or is_remote_or_data_url(src):
        return None

    # markdown image may be: path "title"
    m = re.match(r'^(\S+)(?:\s+["\'].*["\'])?$', src)
    if m:
        src = m.group(1)

    src = unquote(src)
    candidate = Path(src)
    if not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    if not candidate.exists() or not candidate.is_file():
        fail(f"local image not found: {candidate}")
    return candidate


def list_images(image_dir: Path) -> List[Path]:
    files = [
        p
        for p in image_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    return sorted(files, key=lambda p: p.name.lower())


def build_imagepost_html(title: str, image_urls: List[str]) -> str:
    parts: List[str] = [f"<h1>{html_escape(title)}</h1>"]
    for idx, url in enumerate(image_urls, start=1):
        parts.append(
            f'<p><img src="{html_escape(url)}" alt="图{idx}" style="max-width:100%;" /></p>'
        )
    return "\n".join(parts)


def extract_markdown_title(md_content: str) -> Optional[str]:
    for line in md_content.splitlines():
        m = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if m:
            return m.group(1).strip()
    return None


def extract_markdown_digest(md_content: str) -> Optional[str]:
    for line in md_content.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#") or s.startswith("![") or s.startswith(">") or s.startswith("-"):
            continue
        return s[:120]
    return None


def format_inline_markdown(text: str) -> str:
    # Escape first, then apply a few light markdown inline transforms.
    escaped = html_escape(text)

    # [text](url)
    def _link_repl(m: re.Match) -> str:
        label = m.group(1)
        url = m.group(2)
        return f'<a href="{html_escape(url)}">{html_escape(label)}</a>'

    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link_repl, escaped)
    # **bold**
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    # *italic*
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    return escaped


def render_markdown_to_html_with_upload(
    md_path: Path, access_token: str, cache: Dict[str, str]
) -> Tuple[str, Optional[str], Optional[Path]]:
    md_text = md_path.read_text(encoding="utf-8", errors="ignore")
    inferred_title = extract_markdown_title(md_text)
    lines = md_text.splitlines()

    html_blocks: List[str] = []
    paragraph_buffer: List[str] = []
    first_local_image: Optional[Path] = None
    base_dir = md_path.parent

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer
        if paragraph_buffer:
            text = " ".join(paragraph_buffer).strip()
            if text:
                html_blocks.append(f"<p>{format_inline_markdown(text)}</p>")
        paragraph_buffer = []

    image_line_re = re.compile(r"^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$")
    heading_re = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            flush_paragraph()
            continue

        hm = heading_re.match(line)
        if hm:
            flush_paragraph()
            level = len(hm.group(1))
            text = hm.group(2)
            html_blocks.append(f"<h{level}>{format_inline_markdown(text)}</h{level}>")
            continue

        im = image_line_re.match(line)
        if im:
            flush_paragraph()
            alt = im.group(1).strip() or "image"
            raw_src = im.group(2).strip()
            local_path = resolve_local_path(raw_src, base_dir)
            if local_path is None:
                img_url = raw_src
            else:
                if first_local_image is None:
                    first_local_image = local_path
                img_url = upload_content_image(access_token, local_path, cache)
            html_blocks.append(
                f'<p><img src="{html_escape(img_url)}" alt="{html_escape(alt)}" style="max-width:100%;" /></p>'
            )
            continue

        paragraph_buffer.append(line.strip())

    flush_paragraph()
    html_content = "\n".join(html_blocks).strip()
    return html_content, inferred_title, first_local_image


def extract_html_title(html_text: str) -> Optional[str]:
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, flags=re.IGNORECASE | re.DOTALL)
    if h1:
        t = strip_html_tags(h1.group(1))
        if t:
            return t
    title = re.search(
        r"<title[^>]*>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL
    )
    if title:
        t = strip_html_tags(title.group(1))
        if t:
            return t
    return None


def extract_html_digest(html_text: str) -> Optional[str]:
    m = re.search(r"<p[^>]*>(.*?)</p>", html_text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    text = strip_html_tags(m.group(1))
    if not text:
        return None
    return text[:120]


def upload_local_images_in_html(
    html_text: str, base_dir: Path, access_token: str, cache: Dict[str, str]
) -> Tuple[str, Optional[Path]]:
    first_local_image: Optional[Path] = None
    img_src_re = re.compile(
        r'(<img\b[^>]*?\bsrc=)(["\'])([^"\']+)(\2)([^>]*>)',
        flags=re.IGNORECASE,
    )

    def repl(m: re.Match) -> str:
        nonlocal first_local_image
        prefix, q1, src, q2, tail = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        local = resolve_local_path(src, base_dir)
        if local is None:
            return m.group(0)
        if first_local_image is None:
            first_local_image = local
        new_url = upload_content_image(access_token, local, cache)
        return f"{prefix}{q1}{html_escape(new_url)}{q2}{tail}"

    return img_src_re.sub(repl, html_text), first_local_image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Publish WeChat draft by official APIs. "
            "Supports imagepost and article modes."
        )
    )

    parser.add_argument(
        "--mode",
        choices=["imagepost", "article"],
        default="imagepost",
        help="publish mode (default: imagepost)",
    )

    # imagepost mode
    parser.add_argument("--dir", help="Image directory path for imagepost mode")

    # article mode
    parser.add_argument("--markdown", help="Markdown file path for article mode")
    parser.add_argument("--html", dest="html_file", help="HTML file path for article mode")
    parser.add_argument("--content-html", help="Direct HTML content for article mode")

    # shared article fields
    parser.add_argument("--title", help="Article title (<=64 chars)")
    parser.add_argument("--cover", help="Cover image path (default: first local image)")
    parser.add_argument("--author", default="", help="Author name")
    parser.add_argument("--digest", default="", help="Article digest (<=120 chars)")
    parser.add_argument("--source-url", default="", help="Original source URL")

    # auth overrides
    parser.add_argument("--appid", help="WeChat AppID (override env/config)")
    parser.add_argument("--secret", help="WeChat AppSecret (override env/config)")
    parser.add_argument(
        "--force-refresh-token",
        action="store_true",
        help="Force refresh stable token",
    )
    return parser.parse_args()


def infer_mode(args: argparse.Namespace) -> str:
    if args.markdown or args.html_file or args.content_html:
        return "article"
    return args.mode


def resolve_credentials(args: argparse.Namespace) -> Tuple[str, str]:
    appid = args.appid or os.environ.get("WECHAT_APP_ID", "")
    secret = args.secret or os.environ.get("WECHAT_APP_SECRET", "")
    if not appid or not secret:
        fail(
            "Missing WECHAT_APP_ID / WECHAT_APP_SECRET. "
            "Set env vars, or add them to ~/.config/wechat/config "
            "(supports WECHAT_ID/WECHAT_TOKEN), or ~/.openclaw/workspace/TOOLS.md"
        )
    return appid, secret


def run_imagepost_mode(
    args: argparse.Namespace, access_token: str, cache: Dict[str, str]
) -> Tuple[str, str, Optional[Path], Optional[str]]:
    if not args.dir:
        fail("--dir is required in imagepost mode")
    if not args.title:
        fail("--title is required in imagepost mode")

    image_dir = Path(args.dir).expanduser().resolve()
    if not image_dir.exists() or not image_dir.is_dir():
        fail(f"Image directory not found: {image_dir}")

    images = list_images(image_dir)
    if not images:
        fail(f"No images found in directory: {image_dir}")

    cover_candidate = Path(args.cover).expanduser().resolve() if args.cover else images[0]
    ensure_exists_file(cover_candidate, "cover image")

    print(f"Image count: {len(images)}")
    print(f"Cover image: {cover_candidate}")
    print("Step 2/4: uploading content images...")
    urls: List[str] = []
    for idx, image in enumerate(images, start=1):
        print(f"  - [{idx}/{len(images)}] {image.name}")
        urls.append(upload_content_image(access_token, image, cache))

    title = safe_title(args.title)
    content_html = build_imagepost_html(title, urls)
    return title, content_html, cover_candidate, args.digest or None


def run_article_mode(
    args: argparse.Namespace, access_token: str, cache: Dict[str, str]
) -> Tuple[str, str, Optional[Path], Optional[str]]:
    sources = [bool(args.markdown), bool(args.html_file), bool(args.content_html)]
    if sum(sources) != 1:
        fail("article mode requires exactly one of --markdown / --html / --content-html")

    cover_candidate: Optional[Path] = None
    inferred_title: Optional[str] = None
    inferred_digest: Optional[str] = None

    print("Step 2/4: processing article content...")

    if args.markdown:
        md_path = Path(args.markdown).expanduser().resolve()
        ensure_exists_file(md_path, "markdown file")
        md_text = md_path.read_text(encoding="utf-8", errors="ignore")
        inferred_digest = extract_markdown_digest(md_text)
        content_html, inferred_title, cover_candidate = render_markdown_to_html_with_upload(
            md_path, access_token, cache
        )
    elif args.html_file:
        html_path = Path(args.html_file).expanduser().resolve()
        ensure_exists_file(html_path, "html file")
        html_text = html_path.read_text(encoding="utf-8", errors="ignore")
        inferred_title = extract_html_title(html_text)
        inferred_digest = extract_html_digest(html_text)
        content_html, cover_candidate = upload_local_images_in_html(
            html_text, html_path.parent, access_token, cache
        )
    else:
        # direct html content
        content_html = args.content_html or ""
        inferred_title = extract_html_title(content_html)
        inferred_digest = extract_html_digest(content_html)

    if not content_html.strip():
        fail("article content is empty after processing")

    title = safe_title(args.title or inferred_title or "")

    if args.cover:
        cover_candidate = Path(args.cover).expanduser().resolve()
        ensure_exists_file(cover_candidate, "cover image")

    if cover_candidate is None:
        fail(
            "cover image is required for article mode when no local images are found. "
            "Please provide --cover /path/to/cover.jpg"
        )

    digest = args.digest or inferred_digest
    return title, content_html, cover_candidate, digest


def main() -> None:
    args = parse_args()
    load_credentials_from_files()
    appid, secret = resolve_credentials(args)

    mode = infer_mode(args)
    print(f"Mode: {mode}")

    print("Step 1/4: fetching stable token...")
    access_token = get_access_token(appid, secret, args.force_refresh_token)
    cache: Dict[str, str] = {}

    if mode == "imagepost":
        title, content_html, cover_path, digest_candidate = run_imagepost_mode(
            args, access_token, cache
        )
    else:
        title, content_html, cover_path, digest_candidate = run_article_mode(
            args, access_token, cache
        )

    if cover_path is None:
        fail("cover image not resolved")

    print("Step 3/4: uploading cover image for thumb_media_id...")
    thumb_media_id = upload_cover_for_thumb(access_token, cover_path)

    print("Step 4/4: creating draft...")
    digest = safe_digest(args.digest or digest_candidate)
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
