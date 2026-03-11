#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from state import DONE, FAILED, RUNNING, set_artifact, set_step
from utils import run


WECHAT_ARTICLE = Path(
    "/Users/aki/Development/code/aki-skills/skills/aki-post-to-wechat/scripts/wechat-article.ts"
)
WECHAT_IMAGEPOST_BROWSER = Path(
    "/Users/aki/Development/code/aki-skills/skills/aki-post-to-wechat/scripts/wechat-browser.ts"
)


def _run_cmd(cmd: list[str], env: dict[str, str] | None = None) -> dict:
    cp = subprocess.run(cmd, text=True, capture_output=True, env=env)
    return {
        "command": cmd,
        "exit_code": cp.returncode,
        "stdout": cp.stdout.strip(),
        "stderr": cp.stderr.strip(),
        "ok": cp.returncode == 0,
    }


def _browser_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        env.pop(key, None)
    env["NO_PROXY"] = "*"
    bun_bin = os.getenv("BUN_BIN") or os.getenv("BUN_PATH")
    if not bun_bin:
        for candidate in (
            Path.home() / ".bun" / "bin" / "bun",
            Path("/opt/homebrew/bin/bun"),
            Path("/usr/local/bin/bun"),
        ):
            if candidate.exists():
                bun_bin = str(candidate)
                break
    if bun_bin:
        env["BUN_BIN"] = bun_bin
        env["BUN_PATH"] = bun_bin
    return env


def _resolve_bun_bin() -> str:
    for candidate in (
        os.getenv("BUN_BIN"),
        os.getenv("BUN_PATH"),
        str(Path.home() / ".bun" / "bin" / "bun"),
        "/opt/homebrew/bin/bun",
        "/usr/local/bin/bun",
        "bun",
    ):
        if not candidate:
            continue
        if candidate == "bun":
            return candidate
        if Path(candidate).expanduser().exists():
            return str(Path(candidate).expanduser())
    return "bun"


def _extract_h1_title(markdown_path: Path, fallback: str = "微信贴图") -> str:
    text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            title = line[2:].strip()
            return title or fallback
        break
    return fallback


def _list_publish_images(images_dir: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in images_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}
        ],
        key=lambda item: item.name.lower(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish WeChat article + imagepost drafts via browser automation")
    parser.add_argument("--topic-root", required=True)
    parser.add_argument(
        "--profile",
        default=str(Path.home() / ".local" / "share" / "wechat-browser-profile"),
        help="Chrome profile directory",
    )
    parser.add_argument("--article-markdown", default="mp_weixin/article/wechat_article.md")
    parser.add_argument("--imagepost-markdown", default="mp_weixin/imagepost/wechat_imagepost_copy.md")
    parser.add_argument("--images-dir", default="mp_weixin/imagepost/images")
    parser.add_argument("--only", choices=["both", "article", "imagepost"], default="article")
    parser.add_argument("--article-style", default="", help="Style preset passed to wechat-article.ts in markdown mode")
    parser.add_argument("--dry-run", action="store_true", help="Print commands and write report without executing publish")
    args = parser.parse_args()

    topic_root = Path(args.topic_root).expanduser().resolve()
    article_md = (topic_root / args.article_markdown).resolve()
    imagepost_md = (topic_root / args.imagepost_markdown).resolve()
    images_dir = (topic_root / args.images_dir).resolve()
    profile_dir = Path(args.profile).expanduser().resolve()

    if args.only in {"both", "article"} and not article_md.exists():
        raise FileNotFoundError(f"Article markdown missing: {article_md}")
    if args.only in {"both", "imagepost"} and not imagepost_md.exists():
        raise FileNotFoundError(f"Imagepost markdown missing: {imagepost_md}")
    if args.only in {"both", "imagepost"} and not images_dir.exists():
        raise FileNotFoundError(f"Imagepost images dir missing: {images_dir}")
    if args.only in {"both", "article"} and not WECHAT_ARTICLE.exists():
        raise FileNotFoundError(f"WeChat article browser script missing: {WECHAT_ARTICLE}")
    if args.only in {"both", "imagepost"} and not WECHAT_IMAGEPOST_BROWSER.exists():
        raise FileNotFoundError(f"WeChat imagepost browser script missing: {WECHAT_IMAGEPOST_BROWSER}")

    publish_images: list[Path] = []
    if args.only in {"both", "imagepost"}:
        publish_images = _list_publish_images(images_dir)
        if not publish_images:
            raise RuntimeError(f"No JPG imagepost images found under {images_dir}")

    if args.only == "both":
        run_message = "Publishing article(browser) + imagepost(browser) drafts"
        done_message = "WeChat article(browser) + imagepost(browser) drafts published"
    elif args.only == "article":
        run_message = "Publishing article draft"
        done_message = "WeChat article draft published"
    else:
        run_message = "Publishing imagepost draft via browser"
        done_message = "WeChat imagepost draft published via browser"

    if args.dry_run:
        run_message = f"{run_message} (dry-run)"
        done_message = f"{done_message} (dry-run)"
    set_step(topic_root, "publish_wechat_drafts", RUNNING, message=run_message)

    bun_bin = _resolve_bun_bin()
    article_cmd = [
        bun_bin,
        str(WECHAT_ARTICLE),
        "--markdown",
        str(article_md),
        "--submit",
        "--profile",
        str(profile_dir),
    ]
    if args.article_style:
        article_cmd.extend(["--style", args.article_style])
    imagepost_cmd = [
        bun_bin,
        str(WECHAT_IMAGEPOST_BROWSER),
        "--intent",
        "imagepost",
        "--markdown",
        str(imagepost_md),
        "--images",
        str(images_dir),
        "--submit",
        "--pre-submit-settings",
        "--profile",
        str(profile_dir),
    ]

    report: dict[str, dict] = {
        "mode": {"selected": args.only, "dry_run": args.dry_run},
        "routes": {"article": "browser", "imagepost": "browser"},
        "article_style": args.article_style or None,
    }
    if args.only in {"both", "article"}:
        report["article"] = (
            {"command": article_cmd, "exit_code": 0, "stdout": "", "stderr": "", "ok": True, "skipped": "dry-run"}
            if args.dry_run
            else _run_cmd(article_cmd)
        )
    if args.only in {"both", "imagepost"}:
        report["imagepost_assets"] = {
            "images_dir": str(images_dir),
            "image_count": len(publish_images),
            "images": [str(path) for path in publish_images],
            "pre_submit_settings": True,
        }
        report["imagepost"] = (
            {"command": imagepost_cmd, "exit_code": 0, "stdout": "", "stderr": "", "ok": True, "skipped": "dry-run"}
            if args.dry_run
            else _run_cmd(imagepost_cmd, env=_browser_env())
        )
    report_path = topic_root / "meta" / "wechat_publish_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    set_artifact(topic_root, "wechat_publish_report", str(report_path))

    publish_rows = [report[key] for key in ("article", "imagepost") if key in report]
    if any(not row.get("ok", False) for row in publish_rows):
        set_step(
            topic_root,
            "publish_wechat_drafts",
            FAILED,
            message="At least one WeChat publish action failed",
            meta={"report": str(report_path)},
        )
        print(str(report_path))
        return 1

    set_step(
        topic_root,
        "publish_wechat_drafts",
        DONE,
        message=done_message,
        meta={"report": str(report_path)},
    )
    print(str(report_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
