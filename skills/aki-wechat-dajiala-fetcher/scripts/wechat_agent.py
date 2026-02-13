#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import html as html_lib
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib import error, parse, request

BASE_URL = "https://www.dajiala.com"
POST_HISTORY_PATH = "/fbmain/monitor/v3/post_history"
ARTICLE_DETAIL_PATH = "/fbmain/monitor/v3/article_detail"
ARTICLE_INFO_PATH = "/fbmain/monitor/v3/article_info"
ARTICLE_COMMENT_PATH = "/fbmain/monitor/v3/article_comment2"

DEFAULT_MODE = 2
DEFAULT_MIN_INTERVAL = 1.2
DEFAULT_OUTPUT = "/Users/aki/Downloads/Browsers/自媒体"
DEFAULT_TIMEOUT = 30.0
DEFAULT_COMMENT_READ_THRESHOLD = 100000
DEFAULT_CONFIG_CANDIDATES = ("agent.json", "config.json")
DOCS_DIR_NAME = "api_docs"
DEFAULT_DOC_URLS = [
    "https://s.apifox.cn/410674f9-f451-4b4f-957a-5f54f243bc83/199746415e0",
    "https://s.apifox.cn/410674f9-f451-4b4f-957a-5f54f243bc83/220474677e0",
    "https://s.apifox.cn/410674f9-f451-4b4f-957a-5f54f243bc83/api-199746415",
    "https://s.apifox.cn/410674f9-f451-4b4f-957a-5f54f243bc83/199766293e0",
    "https://s.apifox.cn/410674f9-f451-4b4f-957a-5f54f243bc83/199758598e0",
]

RATE_LIMIT_HINTS = [
    "\u9891\u7e41",  # frequent
    "\u8fc7\u5feb",  # too fast
    "\u98ce\u63a7",  # risk control
    "\u9650\u5236",  # limit
]


class Throttler:
    def __init__(self, min_interval: float, jitter: float = 0.3) -> None:
        self.min_interval = max(min_interval, 0.0)
        self.jitter = max(jitter, 0.0)
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        delay = self.min_interval - elapsed
        if delay > 0:
            delay += random.uniform(0.0, self.jitter)
            time.sleep(delay)
        self._last = time.monotonic()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch WeChat official account history and article details via dajiala.com APIs."
        )
    )
    parser.add_argument("--config", help="Config file path (default: agent.json).")
    parser.add_argument("--prompt", help="Natural language prompt that includes a link.")
    parser.add_argument("--url", help="WeChat article URL.")
    parser.add_argument("--biz", help="WeChat official account biz ID.")
    parser.add_argument("--name", help="WeChat official account name or WeChat ID.")
    parser.add_argument("--key", help="API key (or set DAJIALA_KEY).")
    parser.add_argument("--verifycode", help="Verify code if required.")
    parser.add_argument("--mode", type=int, choices=[1, 2], default=None)
    parser.add_argument("--output", default=None, help="Output directory.")
    parser.add_argument("--min-interval", type=float, default=None)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--max-articles", type=int, default=None)
    parser.add_argument("--start-page", type=int, default=None)
    parser.add_argument("--skip-cover", action="store_true")
    parser.add_argument("--no-detail", action="store_true")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Stop listing once an already-downloaded article is encountered.",
    )
    parser.add_argument("--timeout", type=float, default=None)
    return parser.parse_args()


def extract_url(text: str) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"https?://[^\s'\"<>]+", text)
    return match.group(0) if match else None


def extract_biz(text: str) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"__biz=([A-Za-z0-9+/=]+)", text)
    return match.group(1) if match else None


def read_prompt_from_stdin() -> str:
    if not sys.stdin.isatty():
        data = sys.stdin.read().strip()
        if data:
            return data
    try:
        return input("Paste a message or URL: ").strip()
    except EOFError:
        return ""


def is_short_wechat_url(url: str) -> bool:
    return "mp.weixin.qq.com/s/" in url and "__biz=" not in url


def resolve_config_path(cli_value: Optional[str]) -> Optional[Path]:
    if cli_value:
        return Path(cli_value).expanduser()
    env_value = os.getenv("DAJIALA_CONFIG")
    if env_value:
        return Path(env_value).expanduser()
    for name in DEFAULT_CONFIG_CANDIDATES:
        cwd_path = Path.cwd() / name
        if cwd_path.exists():
            return cwd_path
        script_path = Path(__file__).with_name(name)
        if script_path.exists():
            return script_path
    return None


def extract_json_block(text: str) -> Optional[str]:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if match:
        return match.group(1)
    match = re.search(r"```\s*(\{.*?\})\s*```", text, re.S)
    if match:
        return match.group(1)
    return None


def load_config(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"Failed to read config file {path}: {exc}") from exc
    try:
        if path.suffix.lower() in (".md", ".markdown"):
            block = extract_json_block(raw)
            if not block:
                raise SystemExit(
                    f"Config file {path} must include a JSON code block."
                )
            payload = json.loads(block)
        else:
            payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid config file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Config file {path} must be a JSON object.")
    return payload


def safe_slug(value: str, max_len: int = 80) -> str:
    value = value.strip()
    value = re.sub(r"[\\/\\s]+", "_", value)
    value = re.sub(r"[^0-9A-Za-z._-]+", "_", value)
    value = value.strip("._-")
    if not value:
        return ""
    return value[:max_len]


def safe_folder_name(value: str, max_len: int = 80) -> str:
    value = value.strip()
    value = re.sub(r"[\\/]+", "_", value)
    value = re.sub(r"\s+", "_", value)
    value = value.strip("._-")
    if not value:
        return ""
    return value[:max_len]


def sanitize_title_for_filename(value: str, max_len: int = 80) -> str:
    value = value.strip()
    value = value.replace("/", "_").replace("\\", "_")
    value = value.replace(":", "：")
    value = re.sub(r"[\r\n\t]+", " ", value)
    value = re.sub(r'[<>\"|?*]+', "", value)
    value = re.sub(r"\s+", " ", value).strip(" ._-")
    if not value:
        return "article"
    return value[:max_len]


def short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


def http_json(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CodexCLI/1.0)"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {exc.reason}: {body[:200]}")
    except error.URLError as exc:
        raise RuntimeError(f"Request failed: {exc}")

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"Non-JSON response: {body[:200]}")


def http_text(url: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; CodexCLI/1.0)"})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {exc.reason}: {body[:200]}")
    except error.URLError as exc:
        raise RuntimeError(f"Request failed: {exc}")


def should_retry_message(msg: str) -> bool:
    if not msg:
        return False
    return any(hint in msg for hint in RATE_LIMIT_HINTS)


def fetch_json_with_retry(
    url: str,
    method: str,
    payload: Optional[Dict[str, Any]],
    throttler: Throttler,
    timeout: float,
    max_retries: int = 3,
) -> Dict[str, Any]:
    for attempt in range(max_retries + 1):
        throttler.wait()
        try:
            response = http_json(url, method=method, payload=payload, timeout=timeout)
        except RuntimeError as exc:
            if attempt >= max_retries:
                raise
            msg = str(exc)
            if "HTTP 429" in msg or "HTTP 5" in msg:
                time.sleep(2 ** attempt)
                continue
            raise

        if should_retry_message(str(response.get("msg", ""))):
            if attempt >= max_retries:
                return response
            time.sleep(2 ** attempt)
            continue
        return response
    raise RuntimeError("Exceeded retries without a response.")


def update_cost_summary(
    cost_summary: Dict[str, Any],
    payload: Optional[Dict[str, Any]],
    category: str,
) -> None:
    cost = extract_cost(payload)
    if cost is not None:
        cost_summary[f"{category}_cost"] += cost
        cost_summary["total_cost"] += cost
        cost_summary[f"{category}_calls"] += 1
    remain = extract_remain(payload)
    if remain is not None:
        cost_summary["last_remain_money"] = remain


def fetch_article_info(
    url: str,
    key: str,
    verifycode: str,
    throttler: Throttler,
    timeout: float,
) -> Dict[str, Any]:
    payload = {
        "url": url,
        "key": key,
        "verifycode": verifycode,
    }
    info_url = f"{BASE_URL}{ARTICLE_INFO_PATH}"
    return fetch_json_with_retry(
        info_url,
        method="POST",
        payload=payload,
        throttler=throttler,
        timeout=timeout,
    )


def fetch_article_comments(
    url: str,
    key: str,
    verifycode: str,
    throttler: Throttler,
    timeout: float,
    cost_summary: Dict[str, Any],
    max_cost: Optional[float],
    max_pages: Optional[int],
) -> Tuple[Optional[Dict[str, Any]], bool]:
    pages: List[Dict[str, Any]] = []
    buffer = ""
    budget_exceeded = False
    page = 0

    while True:
        payload = {
            "url": url,
            "buffer": buffer,
            "key": key,
            "verifycode": verifycode,
        }
        try:
            response = fetch_json_with_retry(
                f"{BASE_URL}{ARTICLE_COMMENT_PATH}",
                method="POST",
                payload=payload,
                throttler=throttler,
                timeout=timeout,
            )
        except RuntimeError as exc:
            pages.append({"code": -1, "msg": str(exc), "buffer": buffer})
            break

        pages.append(response)
        update_cost_summary(cost_summary, response, "comment")
        if max_cost is not None and cost_summary["total_cost"] >= max_cost:
            budget_exceeded = True
            break

        if response.get("code") not in (0, "0"):
            break

        buffer_value = response.get("buffer")
        if isinstance(buffer_value, str):
            buffer = buffer_value
        else:
            buffer = ""
        page += 1
        if max_pages and page >= max_pages:
            break
        if not buffer:
            break
        if response.get("continue_flag") is False:
            break

    if not pages:
        return None, budget_exceeded

    total = None
    for entry in pages:
        if total is None:
            total = parse_count(entry.get("total"))
    summary = {
        "url": url,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": total,
        "page_count": len(pages),
        "pages": pages,
    }
    return summary, budget_exceeded


def pick_list_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("list", "items", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def pick_cover_url(item: Dict[str, Any]) -> Optional[str]:
    for key in ("cover_url", "pic_cdn_url_1_1", "pic_cdn_url_235_1", "pic_cdn_url_16_9"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def resolve_article_url(detail: Optional[Dict[str, Any]], fallback: str) -> str:
    if detail:
        value = detail.get("url")
        if isinstance(value, str) and value:
            return value
    return fallback


def build_item_from_detail(detail: Dict[str, Any], url: str) -> Dict[str, Any]:
    item: Dict[str, Any] = {"url": url}
    title = detail.get("title") or detail.get("msg_title")
    if isinstance(title, str) and title:
        item["title"] = title
    digest = detail.get("desc") or detail.get("digest")
    if isinstance(digest, str) and digest:
        item["digest"] = digest
    pubtime = detail.get("pubtime") or detail.get("create_time")
    if isinstance(pubtime, str) and pubtime:
        item["post_time_str"] = pubtime
    cover_url = (
        detail.get("cdn_url")
        or detail.get("cdn_url_1_1")
        or detail.get("cdn_url_235_1")
    )
    if isinstance(cover_url, str) and cover_url:
        item["cover_url"] = cover_url
    return item


def extract_info_item(info_payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(info_payload, dict):
        return None
    data = info_payload.get("data")
    if isinstance(data, list) and data:
        if isinstance(data[0], dict):
            return data[0]
    if isinstance(data, dict):
        return data
    return None


def extract_article_ids(
    detail_payload: Optional[Dict[str, Any]],
    info_payload: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    ids: Dict[str, Any] = {}
    if isinstance(detail_payload, dict):
        for key in ("biz", "mid", "idx", "hashid", "comment_id", "user_name", "alias"):
            value = detail_payload.get(key)
            if value not in (None, "", -1):
                ids[key] = value
    info_item = extract_info_item(info_payload) or {}
    for key in ("wxid", "ghid", "hashid"):
        value = info_item.get(key)
        if value not in (None, "", -1):
            ids.setdefault(key, value)
    return ids or None


def collect_article_metrics(
    item: Dict[str, Any],
    detail_payload: Optional[Dict[str, Any]],
    info_payload: Optional[Dict[str, Any]],
    comments_payload: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    original = None
    if detail_payload:
        original = parse_flag(detail_payload.get("copyright_stat"))
    if original is None:
        original = parse_flag(item.get("original"))
    if original is not None:
        metrics["original"] = original

    info_item = extract_info_item(info_payload) or {}
    read = parse_count(info_item.get("read"))
    if read is None and detail_payload:
        read = parse_count(detail_payload.get("read"))
    if read is not None:
        metrics["read"] = read

    praise = parse_count(info_item.get("praise"))
    if praise is None and detail_payload:
        praise = parse_count(detail_payload.get("zan"))
    if praise is not None:
        metrics["praise"] = praise

    look = parse_count(info_item.get("look"))
    if look is None and detail_payload:
        look = parse_count(detail_payload.get("looking"))
    if look is not None:
        metrics["look"] = look

    comment_total = None
    if isinstance(comments_payload, dict):
        comment_total = parse_count(comments_payload.get("total"))
    if comment_total is None and detail_payload:
        comment_total = parse_count(detail_payload.get("comment_count"))
    if comment_total is not None:
        metrics["comment_total"] = comment_total

    if detail_payload:
        share_count = parse_count(detail_payload.get("share_count"))
        if share_count is not None:
            metrics["share_count"] = share_count
        collect_count = parse_count(detail_payload.get("collect_count"))
        if collect_count is not None:
            metrics["collect_count"] = collect_count

    return metrics


def find_comment_error(comments_payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(comments_payload, dict):
        return None
    pages = comments_payload.get("pages")
    if not isinstance(pages, list):
        return None
    for page in pages:
        if not isinstance(page, dict):
            continue
        code = page.get("code")
        if code not in (0, "0", None):
            return page
    return None


def find_existing_entry(
    index_by_url: Dict[str, Dict[str, Any]],
    urls: Iterable[Optional[str]],
) -> Optional[Dict[str, Any]]:
    for url in urls:
        if isinstance(url, str) and url:
            entry = index_by_url.get(url)
            if entry:
                return entry
    return None


def parse_datetime_string(value: str) -> Optional[str]:
    digits = re.sub(r"[^0-9]", "", value)
    if len(digits) >= 14:
        return f"{digits[:8]}_{digits[8:14]}"
    if len(digits) >= 8:
        return f"{digits[:8]}_000000"
    return None


def extract_post_timestamp(item: Dict[str, Any], detail: Optional[Dict[str, Any]]) -> str:
    candidates: List[str] = []
    if detail:
        for key in ("pubtime", "create_time"):
            if isinstance(detail.get(key), str):
                candidates.append(detail[key])
    if isinstance(item.get("post_time_str"), str):
        candidates.append(item["post_time_str"])
    for text in candidates:
        parsed = parse_datetime_string(text)
        if parsed:
            return parsed
    if item.get("post_time") is not None:
        try:
            ts = int(item["post_time"])
            return time.strftime("%Y%m%d_%H%M%S", time.localtime(ts))
        except (TypeError, ValueError):
            pass
    return "99999999_999999"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def download_file(url: str, path: Path, timeout: float) -> None:
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with request.urlopen(req, timeout=timeout) as resp, path.open("wb") as handle:
        handle.write(resp.read())


def extract_content(detail: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    data = detail.get("data")
    if isinstance(data, dict):
        for key in (
            "content",
            "content_text",
            "text",
        ):
            value = data.get(key)
            if isinstance(value, str) and value:
                return key, value
    for key in ("content", "content_text", "text"):
        value = detail.get(key)
        if isinstance(value, str) and value:
            return key, value
    if isinstance(data, str) and data:
        return "content", data
    return None


def extract_html_content(detail: Dict[str, Any]) -> Optional[str]:
    data = detail.get("data")
    if isinstance(data, dict):
        for key in ("content_multi_text", "content_html", "html"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    for key in ("content_multi_text", "content_html", "html"):
        value = detail.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def html_to_text(html_text: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", html_text)
    text = re.sub(r"(?i)</p>|</section>|</h[1-6]>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def html_to_markdown(html_text: str) -> str:
    def strip_tags(value: str) -> str:
        value = re.sub(r"<[^>]+>", "", value)
        return html_lib.unescape(value)

    def extract_attr(tag: str, names: List[str]) -> Optional[str]:
        for name in names:
            match = re.search(
                rf"\b{name}\s*=\s*['\"]([^'\"]+)['\"]",
                tag,
                re.I,
            )
            if match:
                return match.group(1)
        return None

    def replace_img(match: re.Match) -> str:
        tag = match.group(0)
        url = extract_attr(tag, ["data-src", "data-original", "src"])
        if not url:
            return ""
        return f"![image]({url})"

    def replace_link(match: re.Match) -> str:
        tag = match.group(0)
        href = extract_attr(tag, ["href"]) or ""
        text = strip_tags(match.group(1)).strip() or href
        return f"[{text}]({href})" if href else text

    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\\1>", "", html_text)
    for level in range(6, 0, -1):
        text = re.sub(
            rf"(?is)<h{level}[^>]*>(.*?)</h{level}>",
            lambda m, lvl=level: f"\n{'#' * lvl} {strip_tags(m.group(1)).strip()}\n",
            text,
        )
    text = re.sub(r"(?is)<a[^>]*>(.*?)</a>", replace_link, text)
    text = re.sub(r"(?is)<img[^>]*>", replace_img, text)
    text = re.sub(r"(?i)<(strong|b)[^>]*>", "**", text)
    text = re.sub(r"(?i)</(strong|b)>", "**", text)
    text = re.sub(r"(?i)<(em|i)[^>]*>", "*", text)
    text = re.sub(r"(?i)</(em|i)>", "*", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?i)<p[^>]*>", "", text)
    text = re.sub(r"(?i)</section>", "\n", text)
    text = re.sub(r"(?i)<section[^>]*>", "", text)
    text = re.sub(r"(?i)<ul[^>]*>|</ul>|<ol[^>]*>|</ol>", "", text)
    text = re.sub(r"(?i)<li[^>]*>", "\n- ", text)
    text = re.sub(r"(?i)</li>", "", text)
    text = re.sub(r"(?i)<blockquote[^>]*>", "\n> ", text)
    text = re.sub(r"(?i)</blockquote>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = re.sub(r"\*\*\s*\n\s*\*\*", "\n", text)
    text = re.sub(r"\*\*\s*\*\*", "", text)
    lines = [
        line
        for line in text.splitlines()
        if not re.match(r"^\s*(\*\*|__|\*|_)\s*$", line)
    ]
    text = "\n".join(lines).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def extract_text_content(detail: Dict[str, Any]) -> Optional[str]:
    content = extract_content(detail)
    if content:
        _, text = content
        return text
    html_content = extract_html_content(detail)
    if html_content:
        return html_to_text(html_content)
    return None


def extract_account_name(payload: Optional[Dict[str, Any]]) -> Optional[str]:
    if not payload:
        return None
    for key in ("nick_name", "nickname", "account_name", "name", "biz_nickname"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("nick_name", "nickname", "account_name", "name", "biz_nickname"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def derive_base_from_entry(entry: Dict[str, Any]) -> Optional[str]:
    md_path = entry.get("md_path")
    if isinstance(md_path, str):
        return Path(md_path).stem
    html_path = entry.get("html_path")
    if isinstance(html_path, str):
        return Path(html_path).stem
    detail_path = entry.get("detail_path")
    if isinstance(detail_path, str):
        name = Path(detail_path).name
        if name.endswith("_detail.json"):
            return name[: -len("_detail.json")]
    list_path = entry.get("list_item_path")
    if isinstance(list_path, str):
        name = Path(list_path).name
        if name.endswith("_list.json"):
            return name[: -len("_list.json")]
    return None


def load_index_entries(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("articles"), list):
        return [item for item in payload["articles"] if isinstance(item, dict)]
    return []


def read_json_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def detail_has_content(payload: Dict[str, Any]) -> bool:
    return extract_text_content(payload) is not None or extract_html_content(payload) is not None


def detail_is_ok(payload: Dict[str, Any]) -> bool:
    code = payload.get("code")
    if code not in (0, "0"):
        return False
    return detail_has_content(payload)


def ensure_unique_base(directory: Path, base: str) -> str:
    candidate = base
    for i in range(1, 1000):
        md_path = directory / f"{candidate}.md"
        if not md_path.exists():
            return candidate
        candidate = f"{base}_{i + 1}"
    return f"{base}_{short_hash(base)}"


def build_markdown(
    item: Dict[str, Any],
    detail: Optional[Dict[str, Any]],
    url: str,
    cover_rel: Optional[str],
    account_name: Optional[str],
    info_payload: Optional[Dict[str, Any]] = None,
    comments_payload: Optional[Dict[str, Any]] = None,
) -> str:
    title = (
        (detail or {}).get("title")
        or item.get("title")
        or item.get("digest")
        or "Untitled"
    )
    author = (detail or {}).get("author") or ""
    pubtime = (
        (detail or {}).get("pubtime")
        or (detail or {}).get("create_time")
        or item.get("post_time_str")
        or ""
    )

    lines = [f"# {title}", ""]
    if account_name:
        lines.append(f"- 公众号：{account_name}")
    if author:
        lines.append(f"- 作者：{author}")
    if pubtime:
        lines.append(f"- 发布时间：{pubtime}")
    lines.append(f"- 原文链接：{url}")

    metrics = collect_article_metrics(item, detail, info_payload, comments_payload)
    if "read" in metrics:
        lines.append(f"- 阅读数：{metrics['read']}")
    if "praise" in metrics:
        lines.append(f"- 点赞数：{metrics['praise']}")
    if "look" in metrics:
        lines.append(f"- 在看数：{metrics['look']}")
    if "comment_total" in metrics:
        lines.append(f"- 评论数：{metrics['comment_total']}")
    if "share_count" in metrics:
        lines.append(f"- 转发数：{metrics['share_count']}")
    if "collect_count" in metrics:
        lines.append(f"- 收藏数：{metrics['collect_count']}")
    if "original" in metrics:
        lines.append(f"- 是否原创：{'是' if metrics['original'] else '否'}")
    if cover_rel:
        lines.extend(["", f"![cover]({cover_rel})"])

    body_text = None
    if detail:
        html_content = extract_html_content(detail)
        if html_content:
            body_text = html_to_markdown(html_content)
        else:
            body_text = extract_text_content(detail)
    if body_text:
        lines.extend(["", body_text])
    elif item.get("digest"):
        lines.extend(["", item.get("digest", "")])
    return "\n".join(lines).strip() + "\n"


def build_html_document(title: str, body_html: str) -> str:
    body_html = ensure_img_src(body_html)
    if re.search(r"<\s*html\b", body_html, re.I):
        return body_html
    safe_title = html_lib.escape(title or "WeChat Article")
    return (
        "<!doctype html>"
        "<html><head><meta charset=\"utf-8\">"
        f"<title>{safe_title}</title>"
        "</head><body>"
        f"{body_html}"
        "</body></html>"
    )


def ensure_img_src(html_text: str) -> str:
    def repl(match: re.Match) -> str:
        tag = match.group(0)
        if re.search(r"\bsrc\s*=", tag, re.I):
            return tag
        data_src = re.search(r"\bdata-src\s*=\s*['\"]([^'\"]+)['\"]", tag, re.I)
        if not data_src:
            data_src = re.search(
                r"\bdata-original\s*=\s*['\"]([^'\"]+)['\"]", tag, re.I
            )
        if not data_src:
            return tag
        url = data_src.group(1)
        tag = tag.rstrip(">")
        return f"{tag} src=\"{url}\">"

    return re.sub(r"(?is)<img\b[^>]*>", repl, html_text)


def load_doc_index(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
        return payload["entries"]
    return []


def save_api_docs(
    docs_dir: Path,
    urls: Iterable[str],
    timeout: float,
) -> List[Dict[str, Any]]:
    ensure_dir(docs_dir)
    index_path = docs_dir / "index.json"
    index_entries = load_doc_index(index_path)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_id = f"{timestamp}_{time.time_ns() % 1000000:06d}"
    saved_entries: List[Dict[str, Any]] = []

    for url in urls:
        if not isinstance(url, str) or not url.strip():
            continue
        parsed = parse.urlparse(url)
        slug = safe_slug(Path(parsed.path).name) or safe_slug(parsed.path) or "doc"
        suffix = short_hash(url)
        filename = f"{run_id}_{slug}_{suffix}.html"
        path = docs_dir / filename
        try:
            content = http_text(url, timeout=timeout)
            path.write_text(content, encoding="utf-8")
            entry = {
                "url": url,
                "saved_at": run_id,
                "file": str(path),
            }
            index_entries.append(entry)
            saved_entries.append(entry)
        except RuntimeError as exc:
            entry = {
                "url": url,
                "saved_at": run_id,
                "error": str(exc),
            }
            index_entries.append(entry)
            saved_entries.append(entry)

    write_json(index_path, {"entries": index_entries})
    return saved_entries


def to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1"):
            return True
        if lowered in ("false", "no", "0"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def extract_cost(payload: Optional[Dict[str, Any]]) -> Optional[float]:
    if not isinstance(payload, dict):
        return None
    for key in ("cost_money", "cost"):
        value = to_float(payload.get(key))
        if value is not None:
            return value
    return None


def extract_remain(payload: Optional[Dict[str, Any]]) -> Optional[float]:
    if not isinstance(payload, dict):
        return None
    for key in ("remain_money", "remain"):
        value = to_float(payload.get(key))
        if value is not None:
            return value
    return None


def parse_flag(value: Any) -> Optional[bool]:
    if value in (1, "1", True):
        return True
    if value in (0, "0", False):
        return False
    return None


def parse_count(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        if value < 0:
            return None
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        match = re.match(r"([0-9]+(?:\.[0-9]+)?)\s*(万|w|W)\+?", text)
        if match:
            return int(float(match.group(1)) * 10000)
        digits = re.sub(r"[^0-9]", "", text)
        if digits:
            return int(digits)
    return None


def resolve_target(args: argparse.Namespace) -> Tuple[str, str]:
    if args.biz:
        return "biz", args.biz
    if args.url:
        return "url", args.url
    if args.name:
        return "name", args.name
    prompt = args.prompt or ""
    url = extract_url(prompt)
    if url:
        return "url", url
    biz = extract_biz(prompt)
    if biz:
        return "biz", biz
    raise RuntimeError("No target found. Provide --url, --biz, --name, or --prompt.")


def build_account_dir(output_root: Path, label: str) -> Path:
    safe = safe_folder_name(label) or f"account_{short_hash(label)}"
    path = output_root / safe
    ensure_dir(path)
    return path


def move_account_dir(current_dir: Path, target_dir: Path) -> Path:
    if current_dir == target_dir:
        ensure_dir(target_dir)
        return target_dir
    ensure_dir(target_dir)
    if current_dir.exists():
        for item in current_dir.iterdir():
            shutil.move(str(item), target_dir / item.name)
        try:
            current_dir.rmdir()
        except OSError:
            pass
    return target_dir


def migrate_legacy_files(account_dir: Path, md_dir: Path, html_dir: Path) -> None:
    ensure_dir(md_dir)
    ensure_dir(html_dir)
    for item in account_dir.iterdir():
        if not item.is_file():
            continue
        if item.suffix not in (".md", ".html"):
            continue
        target_dir = md_dir if item.suffix == ".md" else html_dir
        target = target_dir / item.name
        if target.exists():
            target = target_dir / f"{item.stem}_legacy{item.suffix}"
        shutil.move(str(item), target)


def relative_path(from_dir: Path, to_path: Path) -> str:
    return os.path.relpath(str(to_path), str(from_dir))


def build_article_base(
    item: Dict[str, Any], detail: Optional[Dict[str, Any]], url: str
) -> str:
    title = str(
        (detail or {}).get("title") or item.get("title") or item.get("digest") or "article"
    )
    timestamp = extract_post_timestamp(item, detail)
    safe_title = sanitize_title_for_filename(title, max_len=80)
    base = f"{timestamp}_{safe_title}"
    return base[:140]


def persist_article(
    *,
    item: Dict[str, Any],
    detail_payload: Optional[Dict[str, Any]],
    info_payload: Optional[Dict[str, Any]],
    comments_payload: Optional[Dict[str, Any]],
    url: str,
    account_dir: Path,
    md_dir: Path,
    html_dir: Path,
    raw_dir: Path,
    assets_dir: Path,
    account_name: Optional[str],
    existing_base: Optional[str],
    retry_needed: bool,
    rewrite_md: bool,
    skip_cover: bool,
    timeout: float,
    errors: List[Dict[str, Any]],
) -> Dict[str, Any]:
    ensure_dir(md_dir)
    ensure_dir(html_dir)
    ensure_dir(raw_dir)
    ensure_dir(assets_dir)

    base = existing_base or build_article_base(item, detail_payload, url)
    base = base if existing_base else ensure_unique_base(md_dir, base)

    list_item_path = raw_dir / f"{base}_list.json"
    if not list_item_path.exists():
        write_json(list_item_path, item)

    detail_path = raw_dir / f"{base}_detail.json"
    if detail_payload and (retry_needed or not detail_path.exists()):
        write_json(detail_path, detail_payload)

    info_path = raw_dir / f"{base}_info.json"
    if info_payload and (retry_needed or not info_path.exists()):
        write_json(info_path, info_payload)

    comments_path = raw_dir / f"{base}_comments.json"
    if comments_payload and (retry_needed or not comments_path.exists()):
        write_json(comments_path, comments_payload)

    cover_path = None
    if not skip_cover:
        cover_url = pick_cover_url(item)
        if cover_url:
            suffix = Path(parse.urlparse(cover_url).path).suffix or ".jpg"
            cover_path = assets_dir / f"{base}{suffix}"
            if not cover_path.exists():
                try:
                    download_file(cover_url, cover_path, timeout)
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "stage": "cover",
                            "url": cover_url,
                            "error": str(exc),
                        }
                    )

    cover_rel = relative_path(md_dir, cover_path) if cover_path else None
    html_content = extract_html_content(detail_payload) if detail_payload else None
    html_path = html_dir / f"{base}.html"
    if html_content and (retry_needed or rewrite_md or not html_path.exists()):
        title = (
            (detail_payload or {}).get("title")
            or item.get("title")
            or item.get("digest")
            or "WeChat Article"
        )
        html_doc = build_html_document(title, html_content)
        html_path.write_text(html_doc, encoding="utf-8")

    md_path = md_dir / f"{base}.md"
    if retry_needed or rewrite_md or not md_path.exists():
        markdown = build_markdown(
            item,
            detail_payload,
            url,
            cover_rel,
            account_name,
            info_payload=info_payload,
            comments_payload=comments_payload,
        )
        md_path.write_text(markdown, encoding="utf-8")

    metrics = collect_article_metrics(item, detail_payload, info_payload, comments_payload)
    ids = extract_article_ids(detail_payload, info_payload)
    entry = {
        "url": url,
        "title": item.get("title"),
        "post_time": item.get("post_time"),
        "timestamp": extract_post_timestamp(item, detail_payload),
        "md_path": str(md_path.relative_to(account_dir)),
        "html_path": (
            str(html_path.relative_to(account_dir))
            if html_content and html_path.exists()
            else None
        ),
        "list_item_path": str(list_item_path.relative_to(account_dir)),
        "detail_path": (
            str(detail_path.relative_to(account_dir)) if detail_path.exists() else None
        ),
        "info_path": str(info_path.relative_to(account_dir)) if info_path.exists() else None,
        "comments_path": (
            str(comments_path.relative_to(account_dir))
            if comments_path.exists()
            else None
        ),
        "cover_path": cover_rel,
    }
    entry.update(metrics)
    if ids:
        entry["ids"] = ids
    if comments_payload:
        entry["comment_page_count"] = comments_payload.get("page_count")
    return entry


def main() -> None:
    args = parse_args()
    config_path = resolve_config_path(args.config)
    config = load_config(config_path)

    if args.mode is None:
        config_mode = to_int(config.get("mode"))
        args.mode = config_mode if config_mode in (1, 2) else DEFAULT_MODE
    if args.output is None:
        config_output = config.get("output")
        args.output = str(config_output) if config_output else DEFAULT_OUTPUT
    if args.min_interval is None:
        config_interval = to_float(config.get("min_interval"))
        args.min_interval = (
            config_interval if config_interval is not None else DEFAULT_MIN_INTERVAL
        )
    if args.timeout is None:
        config_timeout = to_float(config.get("timeout"))
        args.timeout = config_timeout if config_timeout is not None else DEFAULT_TIMEOUT
    if args.start_page is None:
        config_start_page = to_int(config.get("start_page"))
        args.start_page = config_start_page if config_start_page else 1
    if args.max_pages is None:
        args.max_pages = to_int(config.get("max_pages"))
    if args.max_articles is None:
        args.max_articles = to_int(config.get("max_articles"))

    if not args.skip_cover and config.get("skip_cover") is True:
        args.skip_cover = True
    if not args.no_detail and config.get("no_detail") is True:
        args.no_detail = True

    doc_urls = config.get("doc_urls", DEFAULT_DOC_URLS)
    if isinstance(doc_urls, str):
        doc_urls = [doc_urls]
    if not isinstance(doc_urls, list):
        doc_urls = DEFAULT_DOC_URLS
    save_docs = config.get("save_docs", True)
    retry_failed_detail = to_bool(config.get("retry_failed_detail"))
    if retry_failed_detail is None:
        retry_failed_detail = True
    skip_existing = to_bool(config.get("skip_existing"))
    if skip_existing is None:
        skip_existing = True
    rewrite_md = to_bool(config.get("rewrite_md"))
    if rewrite_md is None:
        rewrite_md = False
    incremental = to_bool(config.get("incremental"))
    if incremental is None:
        incremental = False
    if args.incremental:
        incremental = True
    max_cost = to_float(config.get("max_cost"))
    fetch_article_info_flag = to_bool(config.get("fetch_article_info"))
    if fetch_article_info_flag is None:
        fetch_article_info_flag = True
    fetch_comments_flag = to_bool(config.get("fetch_comments"))
    if fetch_comments_flag is None:
        fetch_comments_flag = True
    comment_read_threshold = to_int(config.get("comment_read_threshold"))
    if comment_read_threshold is None:
        comment_read_threshold = DEFAULT_COMMENT_READ_THRESHOLD
    comment_max_pages = to_int(config.get("comment_max_pages"))

    if not (args.biz or args.url or args.name or args.prompt):
        prompt_text = read_prompt_from_stdin()
        if prompt_text:
            args.prompt = prompt_text

    key = args.key or config.get("key") or os.getenv("DAJIALA_KEY")
    if not key:
        raise SystemExit("Missing API key. Use --key or set DAJIALA_KEY.")
    verifycode = (
        args.verifycode
        or config.get("verifycode")
        or os.getenv("DAJIALA_VERIFYCODE", "")
    )

    target_type, target_value = resolve_target(args)
    output_root = Path(args.output).expanduser()
    ensure_dir(output_root)

    notes: List[str] = []
    docs_saved: List[Dict[str, Any]] = []
    cost_summary = {
        "list_cost": 0.0,
        "detail_cost": 0.0,
        "info_cost": 0.0,
        "comment_cost": 0.0,
        "total_cost": 0.0,
        "list_calls": 0,
        "detail_calls": 0,
        "info_calls": 0,
        "comment_calls": 0,
        "last_remain_money": None,
    }
    budget_exceeded = False
    if save_docs:
        docs_saved = save_api_docs(Path(DOCS_DIR_NAME), doc_urls, args.timeout)
    if target_type == "url" and is_short_wechat_url(target_value):
        note = (
            "Short WeChat URL detected; long URLs are recommended and may return faster."
        )
        notes.append(note)
        print(f"Note: {note}")

    label = target_value
    if target_type == "url":
        biz = extract_biz(target_value)
        if biz:
            label = f"biz_{biz}"
    account_dir = build_account_dir(output_root, label)
    md_dir = account_dir / "md"
    html_dir = account_dir / "html"
    raw_dir = account_dir / "raw"
    assets_dir = account_dir / "assets"
    migrate_legacy_files(account_dir, md_dir, html_dir)

    throttler = Throttler(args.min_interval)
    seen_urls = set()
    index_by_url: Dict[str, Dict[str, Any]] = {}
    existing_urls: set[str] = set()
    loaded_index_dirs: set[Path] = set()
    errors: List[Dict[str, Any]] = []
    account_name: Optional[str] = None

    def load_existing_index_for(directory: Path) -> Optional[str]:
        if directory in loaded_index_dirs:
            return None
        loaded_index_dirs.add(directory)
        index_path = directory / "index.json"
        index_payload = read_json_file(index_path)
        existing_name = None
        if isinstance(index_payload, dict):
            existing_name = extract_account_name(index_payload)
        for entry in load_index_entries(index_path):
            url = entry.get("url")
            if isinstance(url, str) and url:
                index_by_url[url] = entry
                existing_urls.add(url)
        return existing_name

    existing_name = load_existing_index_for(account_dir)
    if account_name is None and existing_name:
        account_name = existing_name

    total_page = None
    if target_type == "url":
        total_page = 1
        detail_payload = None
        detail_fetched = False
        params = {
            "url": target_value,
            "key": key,
            "mode": args.mode,
        }
        if verifycode:
            params["verifycode"] = verifycode
        detail_url = f"{BASE_URL}{ARTICLE_DETAIL_PATH}?{parse.urlencode(params)}"
        try:
            detail_payload = fetch_json_with_retry(
                detail_url,
                method="GET",
                payload=None,
                throttler=throttler,
                timeout=args.timeout,
            )
            detail_fetched = True
        except RuntimeError as exc:
            errors.append({"stage": "detail", "url": target_value, "error": str(exc)})

        if detail_fetched:
            update_cost_summary(cost_summary, detail_payload, "detail")
            if max_cost is not None and cost_summary["total_cost"] >= max_cost:
                notes.append(f"Stopped: cost reached limit {max_cost}.")
                budget_exceeded = True

        if detail_payload and detail_payload.get("code") not in (0, "0", None):
            errors.append(
                {"stage": "detail", "url": target_value, "response": detail_payload}
            )

        if detail_payload:
            candidate_name = extract_account_name(detail_payload)
            if candidate_name:
                account_name = candidate_name
                target_dir = build_account_dir(output_root, account_name)
                account_dir = move_account_dir(account_dir, target_dir)
                md_dir = account_dir / "md"
                html_dir = account_dir / "html"
                raw_dir = account_dir / "raw"
                assets_dir = account_dir / "assets"
                migrate_legacy_files(account_dir, md_dir, html_dir)
                existing_name = load_existing_index_for(account_dir)
                if account_name is None and existing_name:
                    account_name = existing_name

        detail_url_value = resolve_article_url(detail_payload, target_value)
        existing_entry = find_existing_entry(
            index_by_url, (detail_url_value, target_value)
        )
        if existing_entry:
            existing_entry_url = existing_entry.get("url")
            if (
                isinstance(existing_entry_url, str)
                and existing_entry_url != detail_url_value
            ):
                index_by_url.pop(existing_entry_url, None)
                existing_entry["url"] = detail_url_value
                index_by_url[detail_url_value] = existing_entry

        existing_base = (
            None if rewrite_md else derive_base_from_entry(existing_entry)
        ) if existing_entry else None
        existing_detail_payload = None
        existing_detail_ok = False
        if existing_entry:
            detail_path_value = existing_entry.get("detail_path")
            if isinstance(detail_path_value, str):
                existing_detail_payload = read_json_file(account_dir / detail_path_value)
            if existing_detail_payload:
                existing_detail_ok = detail_is_ok(existing_detail_payload)

        retry_needed = bool(existing_entry) and retry_failed_detail and not existing_detail_ok
        if skip_existing and existing_entry and not retry_needed and not rewrite_md:
            pass
        else:
            detail_payload_to_use = None
            if detail_payload and detail_is_ok(detail_payload):
                detail_payload_to_use = detail_payload
            elif existing_detail_ok:
                detail_payload_to_use = existing_detail_payload
            url_value = resolve_article_url(detail_payload_to_use, detail_url_value)
            if detail_payload_to_use:
                item = build_item_from_detail(detail_payload_to_use, url_value)
                info_payload = None
                comments_payload = None
                info_url_value = resolve_article_url(detail_payload_to_use, url_value)
                existing_info_payload = None
                existing_comments_payload = None
                if existing_entry:
                    info_path_value = existing_entry.get("info_path")
                    if isinstance(info_path_value, str):
                        existing_info_payload = read_json_file(
                            account_dir / info_path_value
                        )
                    comments_path_value = existing_entry.get("comments_path")
                    if isinstance(comments_path_value, str):
                        existing_comments_payload = read_json_file(
                            account_dir / comments_path_value
                        )

                if existing_info_payload:
                    info_payload = existing_info_payload
                elif fetch_article_info_flag and not budget_exceeded:
                    try:
                        info_payload = fetch_article_info(
                            info_url_value,
                            key=key,
                            verifycode=verifycode,
                            throttler=throttler,
                            timeout=args.timeout,
                        )
                        update_cost_summary(cost_summary, info_payload, "info")
                        if max_cost is not None and cost_summary["total_cost"] >= max_cost:
                            notes.append(f"Stopped: cost reached limit {max_cost}.")
                            budget_exceeded = True
                    except RuntimeError as exc:
                        errors.append(
                            {"stage": "info", "url": info_url_value, "error": str(exc)}
                        )
                if info_payload and info_payload.get("code") not in (0, "0", None):
                    errors.append(
                        {
                            "stage": "info",
                            "url": info_url_value,
                            "response": info_payload,
                        }
                    )
                if info_payload and info_payload.get("code") not in (0, "0", None):
                    errors.append(
                        {
                            "stage": "info",
                            "url": info_url_value,
                            "response": info_payload,
                        }
                    )

                read_count = collect_article_metrics(
                    item,
                    detail_payload_to_use,
                    info_payload,
                    existing_comments_payload,
                ).get("read")
                should_fetch_comments = (
                    fetch_comments_flag
                    and read_count is not None
                    and read_count >= comment_read_threshold
                )
                if existing_comments_payload:
                    comments_payload = existing_comments_payload
                elif should_fetch_comments and not budget_exceeded:
                    comments_payload, budget_exceeded = fetch_article_comments(
                        info_url_value,
                        key=key,
                        verifycode=verifycode,
                        throttler=throttler,
                        timeout=args.timeout,
                        cost_summary=cost_summary,
                        max_cost=max_cost,
                        max_pages=comment_max_pages,
                    )
                    if budget_exceeded and max_cost is not None:
                        notes.append(f"Stopped: cost reached limit {max_cost}.")
                comment_error = find_comment_error(comments_payload)
                if comment_error:
                    errors.append(
                        {
                            "stage": "comments",
                            "url": info_url_value,
                            "response": comment_error,
                        }
                    )
                comment_error = find_comment_error(comments_payload)
                if comment_error:
                    errors.append(
                        {
                            "stage": "comments",
                            "url": info_url_value,
                            "response": comment_error,
                        }
                    )

                entry = persist_article(
                    item=item,
                    detail_payload=detail_payload_to_use,
                    info_payload=info_payload,
                    comments_payload=comments_payload,
                    url=url_value,
                    account_dir=account_dir,
                    md_dir=md_dir,
                    html_dir=html_dir,
                    raw_dir=raw_dir,
                    assets_dir=assets_dir,
                    account_name=account_name,
                    existing_base=existing_base,
                    retry_needed=retry_needed,
                    rewrite_md=rewrite_md,
                    skip_cover=args.skip_cover,
                    timeout=args.timeout,
                    errors=errors,
                )
                index_by_url[url_value] = entry
            else:
                notes.append("No article content available for the provided URL.")
    else:
        page = max(args.start_page, 1)
        stop_incremental = False
        while True:
            payload = {
                "biz": "",
                "url": "",
                "name": "",
                "page": page,
                "key": key,
                "verifycode": verifycode,
            }
            payload[target_type] = target_value
            list_url = f"{BASE_URL}{POST_HISTORY_PATH}"
            response = fetch_json_with_retry(
                list_url,
                method="POST",
                payload=payload,
                throttler=throttler,
                timeout=args.timeout,
            )

            update_cost_summary(cost_summary, response, "list")
            if max_cost is not None and cost_summary["total_cost"] >= max_cost:
                notes.append(f"Stopped: cost reached limit {max_cost}.")
                budget_exceeded = True
                break

            if response.get("code") not in (0, "0", None):
                errors.append({"stage": "list", "page": page, "response": response})
                break

            if not account_name:
                candidate_name = extract_account_name(response)
                if candidate_name:
                    account_name = candidate_name
                    target_dir = build_account_dir(output_root, account_name)
                    account_dir = move_account_dir(account_dir, target_dir)
                    md_dir = account_dir / "md"
                    html_dir = account_dir / "html"
                    raw_dir = account_dir / "raw"
                    assets_dir = account_dir / "assets"
                    migrate_legacy_files(account_dir, md_dir, html_dir)
                    existing_name = load_existing_index_for(account_dir)
                    if account_name is None and existing_name:
                        account_name = existing_name

            items = pick_list_items(response)
            if not items:
                break

            total_page = to_int(response.get("total_page", total_page)) or total_page
            now_page = to_int(response.get("now_page", page)) or page

            for item in items:
                if budget_exceeded:
                    break
                url = item.get("url")
                if not isinstance(url, str) or not url:
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                if incremental and url in existing_urls:
                    notes.append("Stopped: encountered existing article in incremental mode.")
                    stop_incremental = True
                    break

                existing_entry = index_by_url.get(url)
                existing_base = (
                    None if rewrite_md else derive_base_from_entry(existing_entry)
                ) if existing_entry else None
                existing_detail_payload = None
                existing_detail_ok = False
                if existing_entry:
                    detail_path_value = existing_entry.get("detail_path")
                    if isinstance(detail_path_value, str):
                        existing_detail_payload = read_json_file(
                            account_dir / detail_path_value
                        )
                    if existing_detail_payload:
                        existing_detail_ok = detail_is_ok(existing_detail_payload)

                retry_needed = (
                    bool(existing_entry)
                    and retry_failed_detail
                    and not existing_detail_ok
                )
                if skip_existing and existing_entry and not retry_needed and not rewrite_md:
                    continue

                detail_payload = existing_detail_payload
                detail_fetched = False
                if not args.no_detail and (retry_needed or not existing_detail_ok):
                    params = {
                        "url": url,
                        "key": key,
                        "mode": args.mode,
                    }
                    if verifycode:
                        params["verifycode"] = verifycode
                    detail_url = (
                        f"{BASE_URL}{ARTICLE_DETAIL_PATH}?"
                        f"{parse.urlencode(params)}"
                    )
                    try:
                        detail_payload = fetch_json_with_retry(
                            detail_url,
                            method="GET",
                            payload=None,
                            throttler=throttler,
                            timeout=args.timeout,
                        )
                        detail_fetched = True
                    except RuntimeError as exc:
                        errors.append(
                            {"stage": "detail", "url": url, "error": str(exc)}
                        )
                if detail_fetched:
                    update_cost_summary(cost_summary, detail_payload, "detail")
                    if max_cost is not None and cost_summary["total_cost"] >= max_cost:
                        notes.append(f"Stopped: cost reached limit {max_cost}.")
                        budget_exceeded = True
                if budget_exceeded:
                    break

                if not account_name:
                    candidate_name = extract_account_name(detail_payload)
                    if candidate_name:
                        account_name = candidate_name
                        target_dir = build_account_dir(output_root, account_name)
                        account_dir = move_account_dir(account_dir, target_dir)
                        md_dir = account_dir / "md"
                        html_dir = account_dir / "html"
                        raw_dir = account_dir / "raw"
                        assets_dir = account_dir / "assets"
                        migrate_legacy_files(account_dir, md_dir, html_dir)
                        existing_name = load_existing_index_for(account_dir)
                        if account_name is None and existing_name:
                            account_name = existing_name

                info_payload = None
                comments_payload = None
                info_url_value = resolve_article_url(detail_payload, url)
                existing_info_payload = None
                existing_comments_payload = None
                if existing_entry:
                    info_path_value = existing_entry.get("info_path")
                    if isinstance(info_path_value, str):
                        existing_info_payload = read_json_file(
                            account_dir / info_path_value
                        )
                    comments_path_value = existing_entry.get("comments_path")
                    if isinstance(comments_path_value, str):
                        existing_comments_payload = read_json_file(
                            account_dir / comments_path_value
                        )

                if existing_info_payload:
                    info_payload = existing_info_payload
                elif fetch_article_info_flag and not budget_exceeded:
                    try:
                        info_payload = fetch_article_info(
                            info_url_value,
                            key=key,
                            verifycode=verifycode,
                            throttler=throttler,
                            timeout=args.timeout,
                        )
                        update_cost_summary(cost_summary, info_payload, "info")
                        if max_cost is not None and cost_summary["total_cost"] >= max_cost:
                            notes.append(f"Stopped: cost reached limit {max_cost}.")
                            budget_exceeded = True
                    except RuntimeError as exc:
                        errors.append(
                            {"stage": "info", "url": info_url_value, "error": str(exc)}
                        )

                read_count = collect_article_metrics(
                    item,
                    detail_payload,
                    info_payload,
                    existing_comments_payload,
                ).get("read")
                should_fetch_comments = (
                    fetch_comments_flag
                    and read_count is not None
                    and read_count >= comment_read_threshold
                )
                if existing_comments_payload:
                    comments_payload = existing_comments_payload
                elif should_fetch_comments and not budget_exceeded:
                    comments_payload, budget_exceeded = fetch_article_comments(
                        info_url_value,
                        key=key,
                        verifycode=verifycode,
                        throttler=throttler,
                        timeout=args.timeout,
                        cost_summary=cost_summary,
                        max_cost=max_cost,
                        max_pages=comment_max_pages,
                    )
                    if budget_exceeded and max_cost is not None:
                        notes.append(f"Stopped: cost reached limit {max_cost}.")

                entry = persist_article(
                    item=item,
                    detail_payload=detail_payload,
                    info_payload=info_payload,
                    comments_payload=comments_payload,
                    url=url,
                    account_dir=account_dir,
                    md_dir=md_dir,
                    html_dir=html_dir,
                    raw_dir=raw_dir,
                    assets_dir=assets_dir,
                    account_name=account_name,
                    existing_base=existing_base,
                    retry_needed=retry_needed,
                    rewrite_md=rewrite_md,
                    skip_cover=args.skip_cover,
                    timeout=args.timeout,
                    errors=errors,
                )
                index_by_url[url] = entry

                if args.max_articles and len(index_by_url) >= args.max_articles:
                    break

            if budget_exceeded:
                break

            if stop_incremental:
                break

            if args.max_articles and len(index_by_url) >= args.max_articles:
                break

            if args.max_pages and page >= args.max_pages:
                break
            if total_page and now_page >= total_page:
                break

            page += 1

    index_articles = list(index_by_url.values())
    index_articles.sort(key=lambda item: item.get("timestamp") or "")

    index = {
        "config_path": str(config_path) if config_path else None,
        "docs_saved": docs_saved,
        "cost_summary": cost_summary,
        "source": {
            "type": target_type,
            "value": target_value,
            "prompt": args.prompt,
        },
        "account_name": account_name,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_page": total_page,
        "article_count": len(index_articles),
        "articles": index_articles,
        "errors": errors,
        "notes": notes,
    }
    write_json(account_dir / "index.json", index)
    print(f"Saved {len(index_articles)} articles to: {account_dir}")
    if cost_summary["total_cost"] > 0:
        print(
            "Cost summary: total {total:.2f}, list {list_cost:.2f}, detail {detail_cost:.2f}, info {info_cost:.2f}, comment {comment_cost:.2f}, last remain {remain}".format(
                total=cost_summary["total_cost"],
                list_cost=cost_summary["list_cost"],
                detail_cost=cost_summary["detail_cost"],
                info_cost=cost_summary["info_cost"],
                comment_cost=cost_summary["comment_cost"],
                remain=cost_summary["last_remain_money"],
            )
        )


if __name__ == "__main__":
    main()
