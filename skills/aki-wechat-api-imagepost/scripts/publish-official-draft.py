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
import subprocess
import string
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple
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
    # subscription draft/add docs: title <= 32
    if len(trimmed) > 32:
        print("WARN: 标题超过 32 字，已自动截断。")
        trimmed = trimmed[:32]
    return trimmed


def safe_digest(digest: Optional[str]) -> str:
    if not digest:
        return ""
    d = digest.strip()
    # subscription draft/add docs: digest <= 128
    if len(d) > 128:
        print("WARN: 摘要超过 128 字，已自动截断。")
        d = d[:128]
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
        hint = build_wechat_error_hint(result)
        message = f"{context} failed"
        if hint:
            message = f"{message}\nHINT: {hint}"
        fail(message, result)


def build_wechat_error_hint(result: Dict) -> str:
    errcode = result.get("errcode")
    errmsg = str(result.get("errmsg") or "")

    if errcode == 40164:
        ip = ""
        m = re.search(r"invalid ip\s+([0-9a-fA-F\.:]+)", errmsg)
        if m:
            ip = m.group(1)
        ip_tip = f" 当前返回 IP: {ip}。" if ip else ""
        return (
            "检测到 IP 白名单拦截。常见原因："
            "1) 刚更新白名单，微信侧尚未生效；"
            "2) token 请求命中旧校验状态；"
            "3) 请求走了代理出口 IP。"
            f"{ip_tip}"
            "建议：等待 1-5 分钟后重试，并加 --force-refresh-token；"
            "必要时临时禁用代理环境变量（HTTP(S)_PROXY/ALL_PROXY，NO_PROXY='*'）。"
        )

    return ""


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


def upload_permanent_image(
    access_token: str, image_path: Path, cache: Dict[str, str]
) -> str:
    key = str(image_path.resolve())
    if key in cache:
        return cache[key]
    media_id = upload_cover_for_thumb(access_token, image_path)
    cache[key] = media_id
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
    article: Dict,
) -> Dict:
    url = f"{DRAFT_ADD_URL}?access_token={quote(access_token)}"
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


def is_markdown_table_separator_row(line: str) -> bool:
    compact = re.sub(r"\s+", "", line.strip())
    return bool(re.match(r"^\|:?-{3,}:?(?:\|:?-{3,}:?)+\|$", compact))


def split_markdown_table_row(line: str) -> List[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def render_markdown_table_html(header_row: str, body_rows: List[str]) -> str:
    header_cells = split_markdown_table_row(header_row)
    row_cells = [split_markdown_table_row(row) for row in body_rows]
    col_count = max([len(header_cells)] + [len(r) for r in row_cells]) if row_cells else len(header_cells)

    def normalize(cells: List[str]) -> List[str]:
        row = list(cells)
        while len(row) < col_count:
            row.append("")
        return row[:col_count]

    thead = "<tr>{}</tr>".format(
        "".join(
            [
                (
                    '<th style="border:1px solid #d0d7de;background:#f6f8fa;'
                    'padding:8px 10px;text-align:left;font-weight:700;">'
                    f"{format_inline_markdown(cell)}</th>"
                )
                for cell in normalize(header_cells)
            ]
        )
    )

    tbody_rows: List[str] = []
    for cells in row_cells:
        tds = "".join(
            [
                (
                    '<td style="border:1px solid #d0d7de;padding:8px 10px;'
                    'vertical-align:top;">'
                    f"{format_inline_markdown(cell)}</td>"
                )
                for cell in normalize(cells)
            ]
        )
        tbody_rows.append(f"<tr>{tds}</tr>")

    return (
        '<table style="width:100%;border-collapse:collapse;margin:18px 0;'
        'font-size:16px;line-height:1.6;">'
        f"<thead>{thead}</thead><tbody>{''.join(tbody_rows)}</tbody></table>"
    )


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
    table_row_re = re.compile(r"^\s*\|.*\|\s*$")
    unordered_list_re = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
    ordered_list_re = re.compile(r"^\s*(\d+)[\.\)]\s+(.+?)\s*$")

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            flush_paragraph()
            i += 1
            continue

        hm = heading_re.match(line)
        if hm:
            flush_paragraph()
            level = len(hm.group(1))
            text = hm.group(2)
            html_blocks.append(f"<h{level}>{format_inline_markdown(text)}</h{level}>")
            i += 1
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
            i += 1
            continue

        if (
            table_row_re.match(line)
            and i + 1 < len(lines)
            and table_row_re.match(lines[i + 1].rstrip())
            and is_markdown_table_separator_row(lines[i + 1])
        ):
            flush_paragraph()
            header_row = line.strip()
            i += 2  # skip header + separator
            body_rows: List[str] = []
            while i < len(lines):
                row_line = lines[i].rstrip()
                if not row_line.strip() or not table_row_re.match(row_line):
                    break
                if is_markdown_table_separator_row(row_line):
                    i += 1
                    continue
                body_rows.append(row_line.strip())
                i += 1

            if body_rows:
                html_blocks.append(render_markdown_table_html(header_row, body_rows))
            else:
                paragraph_buffer.append(header_row)
            continue

        um = unordered_list_re.match(line)
        om = ordered_list_re.match(line)
        if um or om:
            flush_paragraph()
            is_ordered = om is not None
            items: List[str] = []
            while i < len(lines):
                row_line = lines[i].rstrip()
                if not row_line.strip():
                    break

                if is_ordered:
                    lm = ordered_list_re.match(row_line)
                    if not lm:
                        break
                    items.append(f"{lm.group(1)}. {format_inline_markdown(lm.group(2).strip())}")
                else:
                    lm = unordered_list_re.match(row_line)
                    if not lm:
                        break
                    items.append(format_inline_markdown(lm.group(1).strip()))
                i += 1

            for item in items:
                prefix = "" if is_ordered else "• "
                html_blocks.append(
                    '<p style="font-size:18px;line-height:1.9;color:#333;'
                    f'margin:0 0 20px 0;text-align:justify;">{prefix}{item}</p>'
                )
            continue

        paragraph_buffer.append(line.strip())
        i += 1

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


def extract_content_area_html(html_text: str) -> str:
    m = re.search(
        r'<div[^>]*class=["\'][^"\']*content-area[^"\']*["\'][^>]*>([\s\S]*?)</div>',
        html_text,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    m = re.search(
        r'<section[^>]*class=["\'][^"\']*content-area[^"\']*["\'][^>]*>([\s\S]*?)</section>',
        html_text,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    body_match = re.search(r"<body[^>]*>([\s\S]*?)</body>", html_text, flags=re.IGNORECASE)
    if body_match:
        return body_match.group(1).strip()

    return html_text.strip()


def find_md_to_wechat_context_script() -> Path:
    script_candidates: List[Path] = []
    env_script = os.environ.get("AKI_MD_TO_WECHAT_CONTEXT_SCRIPT", "").strip()
    if env_script:
        script_candidates.append(Path(env_script).expanduser())

    current_dir = Path(__file__).resolve().parent
    skills_dir = current_dir.parent.parent
    script_candidates.extend(
        [
            skills_dir / "aki-post-to-wechat" / "scripts" / "md-to-wechat-context.ts",
            Path("/Users/aki/Development/code/aki-skills/skills/aki-post-to-wechat/scripts/md-to-wechat-context.ts"),
            Path("/Users/aki/.codex/skills/aki-post-to-wechat/scripts/md-to-wechat-context.ts"),
        ]
    )

    for candidate in script_candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()

    fail(
        "Cannot find md-to-wechat-context.ts. "
        "Set AKI_MD_TO_WECHAT_CONTEXT_SCRIPT or install aki-post-to-wechat skill."
    )
    return Path("")


def parse_last_json_object(stdout_text: str) -> Dict[str, Any]:
    text = (stdout_text or "").strip()
    if not text:
        fail("context-to-html bridge returned empty stdout")

    # Prefer parsing full stdout first.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Fallback: parse the last JSON object in mixed logs output.
    start = text.rfind("{")
    while start != -1:
        chunk = text[start:].strip()
        try:
            parsed = json.loads(chunk)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        start = text.rfind("{", 0, start)

    fail("Failed to parse JSON result from context-to-html bridge", {"stdout": text[-1200:]})
    return {}


def replace_placeholders_with_local_images(content_html: str, content_images: List[Dict[str, Any]]) -> Tuple[str, Optional[Path]]:
    html = content_html
    first_local_image: Optional[Path] = None

    for item in content_images:
        placeholder = str(item.get("placeholder") or "").strip()
        local_path_raw = str(item.get("localPath") or "").strip()
        if not placeholder or not local_path_raw:
            continue

        local_path = Path(local_path_raw).expanduser().resolve()
        if not local_path.exists():
            continue
        if first_local_image is None:
            first_local_image = local_path

        img_tag = (
            f'<p><img src="{html_escape(str(local_path))}" '
            f'alt="{html_escape(local_path.stem)}" style="max-width:100%;" /></p>'
        )
        para_re = re.compile(
            rf"<p[^>]*>\s*{re.escape(placeholder)}\s*</p>",
            flags=re.IGNORECASE,
        )
        html, count = para_re.subn(img_tag, html)
        if count == 0:
            html = html.replace(placeholder, img_tag)

    return html, first_local_image


def normalize_context_placeholder_blocks(content_html: str) -> str:
    html = content_html
    html = re.sub(
        r"\bIMAGE_PLACEHOLDER_\d+\b",
        lambda m: f"<p>{m.group(0)}</p>",
        html,
    )
    html = re.sub(
        r"<p[^>]*>\s*<p>\s*(IMAGE_PLACEHOLDER_\d+)\s*</p>\s*</p>",
        r"<p>\1</p>",
        html,
        flags=re.IGNORECASE,
    )
    html = re.sub(
        r"<p[^>]*>\s*(</(?:ul|ol)>)\s*(<p[^>]*>\s*IMAGE_PLACEHOLDER_\d+\s*</p>)\s*</p>",
        r"\1\2",
        html,
        flags=re.IGNORECASE,
    )
    return html


def parse_pipe_table_cells_raw(row: str) -> List[str]:
    text = row.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [c.strip() for c in text.split("|")]


def render_pipe_table_html_raw(header_row: str, body_rows: List[str]) -> str:
    header_cells = parse_pipe_table_cells_raw(header_row)
    row_cells = [parse_pipe_table_cells_raw(row) for row in body_rows]
    col_count = max([len(header_cells)] + [len(r) for r in row_cells]) if row_cells else len(header_cells)

    def normalize(cells: List[str]) -> List[str]:
        out = list(cells)
        while len(out) < col_count:
            out.append("")
        return out[:col_count]

    head_html = "<tr>{}</tr>".format(
        "".join(
            [
                (
                    '<th style="border:1px solid #d0d7de;background:#f6f8fa;'
                    'padding:8px 10px;text-align:left;font-weight:700;">'
                    f"{cell}</th>"
                )
                for cell in normalize(header_cells)
            ]
        )
    )

    body_html_rows: List[str] = []
    for cells in row_cells:
        tds = "".join(
            [
                (
                    '<td style="border:1px solid #d0d7de;padding:8px 10px;'
                    f'vertical-align:top;">{cell}</td>'
                )
                for cell in normalize(cells)
            ]
        )
        body_html_rows.append(f"<tr>{tds}</tr>")

    return (
        '<table style="width:100%;border-collapse:collapse;margin:18px 0;'
        'font-size:16px;line-height:1.6;">'
        f"<thead>{head_html}</thead><tbody>{''.join(body_html_rows)}</tbody></table>"
    )


def convert_pipe_table_paragraphs_in_html(content_html: str) -> str:
    lines = content_html.splitlines()
    row_re = re.compile(r"^\s*<p[^>]*>\s*(\|.*\|)\s*</p>\s*$", flags=re.IGNORECASE)
    
    def next_nonblank(idx: int) -> int:
        j = idx
        while j < len(lines) and not lines[j].strip():
            j += 1
        return j

    out: List[str] = []
    i = 0
    while i < len(lines):
        head = row_re.match(lines[i])
        if not head:
            out.append(lines[i])
            i += 1
            continue

        sep_idx = next_nonblank(i + 1)
        if sep_idx >= len(lines):
            out.append(lines[i])
            i += 1
            continue

        sep = row_re.match(lines[sep_idx])
        if not sep or not is_markdown_table_separator_row(sep.group(1)):
            out.append(lines[i])
            i += 1
            continue

        header_row = head.group(1).strip()
        rows: List[str] = []
        j = sep_idx + 1
        while j < len(lines):
            if not lines[j].strip():
                j += 1
                continue
            m = row_re.match(lines[j])
            if not m:
                break
            row = m.group(1).strip()
            if is_markdown_table_separator_row(row):
                j += 1
                continue
            rows.append(row)
            j += 1

        if rows:
            out.append(render_pipe_table_html_raw(header_row, rows))
            i = j
            continue

        out.append(lines[i])
        i += 1

    return "\n".join(out)


def convert_list_tags_to_bullet_paragraphs(content_html: str) -> str:
    html = content_html
    html = re.sub(
        r"<p[^>]*>\s*(</?(?:ul|ol)[^>]*>)\s*</p>",
        r"\1",
        html,
        flags=re.IGNORECASE,
    )

    def _ul_repl(m: re.Match) -> str:
        inner = m.group(1) or ""
        items = re.findall(r"<li[^>]*>([\s\S]*?)</li>", inner, flags=re.IGNORECASE)
        parts: List[str] = []
        for item in items:
            if not strip_html_tags(item):
                continue
            parts.append(
                '<p style="font-size:18px;line-height:1.9;color:#333;'
                f'margin:0 0 20px 0;text-align:justify;">• {item.strip()}</p>'
            )
        return "\n".join(parts)

    def _ol_repl(m: re.Match) -> str:
        inner = m.group(1) or ""
        items = re.findall(r"<li[^>]*>([\s\S]*?)</li>", inner, flags=re.IGNORECASE)
        parts: List[str] = []
        for idx, item in enumerate(items, start=1):
            if not strip_html_tags(item):
                continue
            parts.append(
                '<p style="font-size:18px;line-height:1.9;color:#333;'
                f'margin:0 0 20px 0;text-align:justify;">{idx}. {item.strip()}</p>'
            )
        return "\n".join(parts)

    html = re.sub(r"<ul[^>]*>([\s\S]*?)</ul>", _ul_repl, html, flags=re.IGNORECASE)
    html = re.sub(r"<ol[^>]*>([\s\S]*?)</ol>", _ol_repl, html, flags=re.IGNORECASE)

    # Cleanup malformed leftovers.
    html = re.sub(r"</?(?:ul|ol)[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(
        r"<li[^>]*>([\s\S]*?)</li>",
        lambda m: (
            '<p style="font-size:18px;line-height:1.9;color:#333;'
            f'margin:0 0 20px 0;text-align:justify;">• {(m.group(1) or "").strip()}</p>'
        ),
        html,
        flags=re.IGNORECASE,
    )
    return html


def postprocess_context_content_html(content_html: str) -> str:
    html = normalize_context_placeholder_blocks(content_html)
    html = convert_pipe_table_paragraphs_in_html(html)
    html = convert_list_tags_to_bullet_paragraphs(html)
    return html


def render_markdown_via_context_to_html_with_upload(
    md_path: Path, access_token: str, cache: Dict[str, str], title_override: Optional[str]
) -> Tuple[str, Optional[str], Optional[str], Optional[Path]]:
    bridge_script = find_md_to_wechat_context_script()
    bun_bin = os.environ.get("BUN_BIN") or os.environ.get("BUN_PATH") or "bun"

    temp_dir = Path(tempfile.mkdtemp(prefix="wechat-api-context-"))
    html_out = temp_dir / "article.wechat.html"

    cmd = [bun_bin, str(bridge_script), str(md_path), "--html-out", str(html_out), "--temp-dir", str(temp_dir)]
    if title_override:
        cmd.extend(["--title", title_override])

    proc = subprocess.run(
        cmd,
        cwd=str(md_path.parent),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        fail(
            "context-to-html markdown conversion failed",
            {
                "command": cmd,
                "stderr": (proc.stderr or "")[-2000:],
                "stdout": (proc.stdout or "")[-800:],
            },
        )

    payload = parse_last_json_object(proc.stdout)
    parsed_html_path = str(payload.get("htmlPath") or "").strip()
    html_path = Path(parsed_html_path).expanduser().resolve() if parsed_html_path else html_out
    ensure_exists_file(html_path, "generated wechat html")

    raw_html = html_path.read_text(encoding="utf-8", errors="ignore")
    content_html = extract_content_area_html(raw_html)
    content_html = content_html.replace("\ufeff", "").strip()
    content_html = postprocess_context_content_html(content_html)

    content_images = payload.get("contentImages")
    if not isinstance(content_images, list):
        content_images = []
    content_html, cover_candidate = replace_placeholders_with_local_images(content_html, content_images)

    # Remove H1 in body to avoid duplicated title in WeChat article body.
    content_html = re.sub(r"<h1[^>]*>[\s\S]*?</h1>", "", content_html, flags=re.IGNORECASE).strip()

    content_html, first_local_in_html = upload_local_images_in_html(
        content_html, html_path.parent, access_token, cache
    )
    if cover_candidate is None:
        cover_candidate = first_local_in_html

    inferred_title = str(payload.get("title") or "").strip() or extract_html_title(raw_html)
    inferred_summary = str(payload.get("summary") or "").strip() or extract_html_digest(content_html)
    return content_html, inferred_title or None, inferred_summary or None, cover_candidate


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
    parser.add_argument(
        "--markdown-renderer",
        choices=["context", "basic"],
        default="context",
        help="renderer for --markdown input (default: context)",
    )

    # shared article fields
    parser.add_argument("--title", help="Article title (<=64 chars)")
    parser.add_argument("--cover", help="Cover image path (default: first local image)")
    parser.add_argument(
        "--article-type",
        choices=["news", "newspic"],
        help=(
            "draft article type. "
            "Default: imagepost=newspic, article=news"
        ),
    )
    parser.add_argument(
        "--open-comment",
        action="store_true",
        help="set need_open_comment=1 in draft payload",
    )
    parser.add_argument(
        "--fans-only-comment",
        action="store_true",
        help="set only_fans_can_comment=1 (implies --open-comment)",
    )
    parser.add_argument(
        "--text",
        default="",
        help="text content for newspic image message (optional)",
    )
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


def resolve_comment_flags(args: argparse.Namespace) -> Tuple[int, int]:
    need_open_comment = 1 if args.open_comment else 0
    only_fans_can_comment = 1 if args.fans_only_comment else 0
    if only_fans_can_comment == 1 and need_open_comment == 0:
        # keep behavior sensible if user only passes --fans-only-comment
        need_open_comment = 1
    return need_open_comment, only_fans_can_comment


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
    args: argparse.Namespace,
    access_token: str,
    url_cache: Dict[str, str],
    media_cache: Dict[str, str],
    article_type: str,
    need_open_comment: int,
    only_fans_can_comment: int,
) -> Dict:
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

    title = safe_title(args.title)
    author = args.author.strip()
    digest = safe_digest(args.digest)
    source_url = args.source_url.strip()

    print(f"Image count: {len(images)}")
    print(f"Cover image: {cover_candidate}")
    print(f"Article type: {article_type}")

    if article_type == "newspic":
        print("Step 2/4: uploading permanent images for image_info...")
        image_media_ids: List[str] = []
        for idx, image in enumerate(images, start=1):
            print(f"  - [{idx}/{len(images)}] {image.name}")
            media_id = upload_permanent_image(access_token, image, media_cache)
            image_media_ids.append(media_id)

        text_content = (args.text or digest or title).strip()
        if not text_content:
            text_content = title

        article: Dict = {
            "article_type": "newspic",
            "title": title,
            "content": text_content,
            "image_info": {
                "image_list": [{"image_media_id": mid} for mid in image_media_ids]
            },
            "need_open_comment": need_open_comment,
            "only_fans_can_comment": only_fans_can_comment,
        }
        if author:
            article["author"] = author
        if digest:
            article["digest"] = digest
        if source_url:
            article["content_source_url"] = source_url
        return article

    # news: keep backward-compatible behavior with HTML content + thumb cover.
    print("Step 2/4: uploading content images...")
    urls: List[str] = []
    for idx, image in enumerate(images, start=1):
        print(f"  - [{idx}/{len(images)}] {image.name}")
        urls.append(upload_content_image(access_token, image, url_cache))

    print("Step 3/4: uploading cover image for thumb_media_id...")
    thumb_media_id = upload_permanent_image(access_token, cover_candidate, media_cache)
    content_html = build_imagepost_html(title, urls)
    article = {
        "article_type": "news",
        "title": title,
        "content": content_html,
        "thumb_media_id": thumb_media_id,
        "need_open_comment": need_open_comment,
        "only_fans_can_comment": only_fans_can_comment,
    }
    if author:
        article["author"] = author
    if digest:
        article["digest"] = digest
    if source_url:
        article["content_source_url"] = source_url
    return article


def run_article_mode(
    args: argparse.Namespace,
    access_token: str,
    url_cache: Dict[str, str],
    media_cache: Dict[str, str],
    article_type: str,
    need_open_comment: int,
    only_fans_can_comment: int,
) -> Dict:
    if article_type != "news":
        fail("article mode currently supports article_type=news only")

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

        if args.markdown_renderer == "context":
            print("  - markdown renderer: context-to-html")
            content_html, inferred_title_ctx, inferred_digest_ctx, cover_candidate_ctx = (
                render_markdown_via_context_to_html_with_upload(
                    md_path,
                    access_token,
                    url_cache,
                    args.title.strip() if args.title else None,
                )
            )
            inferred_title = inferred_title_ctx or inferred_title
            inferred_digest = inferred_digest_ctx or inferred_digest
            cover_candidate = cover_candidate_ctx or cover_candidate
        else:
            print("  - markdown renderer: basic")
            content_html, inferred_title, cover_candidate = render_markdown_to_html_with_upload(
                md_path, access_token, url_cache
            )
    elif args.html_file:
        html_path = Path(args.html_file).expanduser().resolve()
        ensure_exists_file(html_path, "html file")
        html_text = html_path.read_text(encoding="utf-8", errors="ignore")
        inferred_title = extract_html_title(html_text)
        inferred_digest = extract_html_digest(html_text)
        content_html, cover_candidate = upload_local_images_in_html(
            html_text, html_path.parent, access_token, url_cache
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

    author = args.author.strip()
    digest = safe_digest(args.digest or inferred_digest)
    source_url = args.source_url.strip()

    print("Step 3/4: uploading cover image for thumb_media_id...")
    thumb_media_id = upload_permanent_image(access_token, cover_candidate, media_cache)

    article: Dict = {
        "article_type": "news",
        "title": title,
        "content": content_html,
        "thumb_media_id": thumb_media_id,
        "need_open_comment": need_open_comment,
        "only_fans_can_comment": only_fans_can_comment,
    }
    if author:
        article["author"] = author
    if digest:
        article["digest"] = digest
    if source_url:
        article["content_source_url"] = source_url
    return article


def main() -> None:
    args = parse_args()
    load_credentials_from_files()
    appid, secret = resolve_credentials(args)

    mode = infer_mode(args)
    default_article_type = "newspic" if mode == "imagepost" else "news"
    article_type = args.article_type or default_article_type
    need_open_comment, only_fans_can_comment = resolve_comment_flags(args)
    print(f"Mode: {mode} (article_type={article_type})")
    if mode == "article":
        print(
            "NOTE: 当前为文章模式。若用户明确要求“图文/贴图”，请改用 imagepost/newspic。"
        )

    print("Step 1/4: fetching stable token...")
    access_token = get_access_token(appid, secret, args.force_refresh_token)
    url_cache: Dict[str, str] = {}
    media_cache: Dict[str, str] = {}

    if mode == "imagepost":
        article = run_imagepost_mode(
            args,
            access_token,
            url_cache,
            media_cache,
            article_type,
            need_open_comment,
            only_fans_can_comment,
        )
    else:
        article = run_article_mode(
            args,
            access_token,
            url_cache,
            media_cache,
            article_type,
            need_open_comment,
            only_fans_can_comment,
        )

    print("Step 4/4: creating draft...")
    result = add_draft(access_token, article)

    media_id = result.get("media_id", "")
    print("SUCCESS: 草稿创建完成。")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if media_id:
        print(f"Draft media_id: {media_id}")


if __name__ == "__main__":
    main()
