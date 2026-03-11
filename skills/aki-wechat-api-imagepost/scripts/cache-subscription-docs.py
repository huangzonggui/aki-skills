#!/usr/bin/env python3
"""
Cache WeChat subscription API docs locally for offline/low-latency reference.

Usage:
  python3 scripts/cache-subscription-docs.py
  python3 scripts/cache-subscription-docs.py --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import time
import urllib.error
from urllib.request import Request, urlopen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cache subscription API docs")
    parser.add_argument(
        "--urls",
        default=None,
        help="Path to URL list file (default: references/subscription-api/subscription-api-urls.txt)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output cache dir (default: references/subscription-api/cache)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if cached file exists",
    )
    return parser.parse_args()


def slugify_url(url: str) -> str:
    # Keep deterministic names and avoid filesystem issues.
    core = url.replace("https://", "").replace("http://", "")
    core = core.replace("/", "__")
    core = core.replace("?", "__q__").replace("&", "__and__").replace("=", "__eq__")
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{core}__{h}.html"


def read_urls(path: Path) -> list[str]:
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        urls.append(s)
    return urls


def fetch(url: str, timeout: int = 60, retries: int = 3) -> bytes:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        req = Request(url, headers={"User-Agent": "aki-wechat-api-doc-cache/1.0"})
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(1.0 * attempt)
                continue
            raise
    if last_err is not None:
        raise last_err
    raise RuntimeError("unexpected fetch failure")


def main() -> None:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    ref_dir = skill_dir / "references" / "subscription-api"

    urls_path = Path(args.urls).expanduser().resolve() if args.urls else (ref_dir / "subscription-api-urls.txt")
    out_dir = Path(args.out).expanduser().resolve() if args.out else (ref_dir / "cache")
    out_dir.mkdir(parents=True, exist_ok=True)

    if not urls_path.exists():
        raise SystemExit(f"URL list not found: {urls_path}")

    urls = read_urls(urls_path)
    if not urls:
        raise SystemExit("No URLs to cache")

    manifest: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "urls_file": str(urls_path),
        "cache_dir": str(out_dir),
        "items": [],
    }

    print(f"Caching {len(urls)} docs to: {out_dir}")
    failed = 0
    for idx, url in enumerate(urls, start=1):
        name = slugify_url(url)
        file_path = out_dir / name

        if file_path.exists() and not args.force:
            size = file_path.stat().st_size
            status = "cached"
            print(f"[{idx}/{len(urls)}] {status:7} {url}")
        else:
            try:
                body = fetch(url)
                file_path.write_bytes(body)
                size = len(body)
                status = "fetched"
                error = ""
                print(f"[{idx}/{len(urls)}] {status:7} {url}")
            except Exception as exc:
                failed += 1
                size = 0
                status = "failed"
                error = str(exc)
                print(f"[{idx}/{len(urls)}] {status:7} {url} -> {error}")

        manifest["items"].append(
            {
                "url": url,
                "file": str(file_path),
                "size": size,
                "status": status,
                "error": error if status == "failed" else "",
            }
        )

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Manifest written: {manifest_path}")
    if failed:
        print(f"Done with failures: {failed}")


if __name__ == "__main__":
    main()
