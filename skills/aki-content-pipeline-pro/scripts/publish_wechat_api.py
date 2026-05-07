#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from state import DONE, FAILED, RUNNING, set_artifact, set_step


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(os.getenv("AKI_SKILLS_REPO_ROOT", "")).expanduser().resolve() if os.getenv("AKI_SKILLS_REPO_ROOT") else SCRIPT_DIR.parents[2]
SHARED_DIR = REPO_ROOT / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from aki_runtime import default_ai_keys_env_path, skill_path  # noqa: E402


WECHAT_API_PUBLISH = skill_path(
    "aki-wechat-api-imagepost",
    "scripts",
    "publish-official-draft.py",
    repo_root_path=REPO_ROOT,
)


def _load_env_file(path: Path, env: dict[str, str]) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value and key not in env:
            env[key] = value


def _api_env() -> dict[str, str]:
    env = os.environ.copy()
    _load_env_file(default_ai_keys_env_path(), env)
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
    return env


def _run_cmd(cmd: list[str], env: dict[str, str]) -> dict:
    cp = subprocess.run(cmd, text=True, capture_output=True, env=env)
    return {
        "command": cmd,
        "exit_code": cp.returncode,
        "stdout": cp.stdout.strip(),
        "stderr": cp.stderr.strip(),
        "ok": cp.returncode == 0,
    }


def _extract_markdown_title_and_text(markdown_path: Path, fallback: str = "微信图文") -> tuple[str, str]:
    text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    title = ""
    body_lines: list[str] = []
    in_front_matter = False
    for idx, raw in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n")):
        line = raw.strip()
        if idx == 0 and line == "---":
            in_front_matter = True
            continue
        if in_front_matter:
            if line == "---":
                in_front_matter = False
                continue
            if not title:
                m = re.match(r"^title:\s*(.+)$", line)
                if m:
                    title = m.group(1).strip().strip("'\"")
            continue
        if not line:
            continue
        if line.startswith("!["):
            continue
        if not title and line.startswith("# "):
            title = line[2:].strip()
            continue
        clean = re.sub(r"^#{1,6}\s*", "", line)
        clean = re.sub(r"^[-*]\s*", "", clean).strip()
        if clean:
            body_lines.append(clean)
    body = "\n".join(body_lines).strip()
    if len(body) > 1800:
        body = body[:1800].rstrip() + "..."
    return title or fallback, body


def _list_publish_images(images_dir: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in images_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        ],
        key=lambda item: item.name.lower(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish WeChat article + imagepost drafts via official APIs")
    parser.add_argument("--topic-root", required=True)
    parser.add_argument("--profile", default="", help="Ignored. Kept for compatibility with the old browser route.")
    parser.add_argument("--article-markdown", default="mp_weixin/article/wechat_article.md")
    parser.add_argument("--imagepost-markdown", default="mp_weixin/imagepost/wechat_imagepost_copy.md")
    parser.add_argument("--images-dir", default="mp_weixin/imagepost/images")
    parser.add_argument("--only", choices=["both", "article", "imagepost"], default="article")
    parser.add_argument("--article-style", default="", help="Ignored by the official API route.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands and write report without executing publish")
    parser.add_argument("--open-comment", action="store_true", default=True)
    parser.add_argument("--force-refresh-token", action="store_true")
    args = parser.parse_args()

    topic_root = Path(args.topic_root).expanduser().resolve()
    article_md = (topic_root / args.article_markdown).resolve()
    imagepost_md = (topic_root / args.imagepost_markdown).resolve()
    images_dir = (topic_root / args.images_dir).resolve()

    if not WECHAT_API_PUBLISH.exists():
        raise FileNotFoundError(f"WeChat API publish script missing: {WECHAT_API_PUBLISH}")
    if args.only in {"both", "article"} and not article_md.exists():
        raise FileNotFoundError(f"Article markdown missing: {article_md}")
    if args.only in {"both", "imagepost"} and not imagepost_md.exists():
        raise FileNotFoundError(f"Imagepost markdown missing: {imagepost_md}")
    if args.only in {"both", "imagepost"} and not images_dir.exists():
        raise FileNotFoundError(f"Imagepost images dir missing: {images_dir}")

    publish_images = _list_publish_images(images_dir) if images_dir.exists() else []
    if args.only in {"both", "imagepost"} and not publish_images:
        raise RuntimeError(f"No publish images found under {images_dir}")

    title, imagepost_text = _extract_markdown_title_and_text(imagepost_md) if imagepost_md.exists() else ("微信图文", "")
    cover = publish_images[0] if publish_images else None
    env = _api_env()
    set_step(
        topic_root,
        "publish_wechat_drafts",
        RUNNING,
        message=("Publishing WeChat drafts via official API" + (" (dry-run)" if args.dry_run else "")),
    )

    report: dict[str, dict] = {
        "mode": {"selected": args.only, "dry_run": args.dry_run},
        "routes": {"article": "official_api", "imagepost": "official_api"},
        "article_style": args.article_style or None,
        "profile_ignored": bool(args.profile),
    }

    def maybe_run(cmd: list[str]) -> dict:
        return {"command": cmd, "exit_code": 0, "stdout": "", "stderr": "", "ok": True, "skipped": "dry-run"} if args.dry_run else _run_cmd(cmd, env)

    common_flags: list[str] = []
    if args.force_refresh_token:
        common_flags.append("--force-refresh-token")
    if args.open_comment:
        common_flags.append("--open-comment")

    if args.only in {"both", "article"}:
        article_cmd = [
            sys.executable,
            str(WECHAT_API_PUBLISH),
            "--mode",
            "article",
            "--markdown",
            str(article_md),
            *common_flags,
        ]
        if cover:
            article_cmd.extend(["--cover", str(cover)])
        report["article"] = maybe_run(article_cmd)

    if args.only in {"both", "imagepost"}:
        imagepost_cmd = [
            sys.executable,
            str(WECHAT_API_PUBLISH),
            "--mode",
            "imagepost",
            "--article-type",
            "newspic",
            "--dir",
            str(images_dir),
            "--title",
            title,
            "--text",
            imagepost_text or title,
            *common_flags,
        ]
        report["imagepost_assets"] = {
            "images_dir": str(images_dir),
            "image_count": len(publish_images),
            "images": [str(path) for path in publish_images],
        }
        report["imagepost"] = maybe_run(imagepost_cmd)

    report_path = topic_root / "meta" / "wechat_publish_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    set_artifact(topic_root, "wechat_publish_report", str(report_path))

    publish_rows = [report[key] for key in ("article", "imagepost") if key in report]
    if any(not row.get("ok", False) for row in publish_rows):
        set_step(
            topic_root,
            "publish_wechat_drafts",
            FAILED,
            message="At least one WeChat official API publish action failed",
            meta={"report": str(report_path)},
        )
        print(str(report_path))
        return 1

    set_step(
        topic_root,
        "publish_wechat_drafts",
        DONE,
        message="WeChat drafts published via official API" + (" (dry-run)" if args.dry_run else ""),
        meta={"report": str(report_path)},
    )
    print(str(report_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
