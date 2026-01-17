#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path
import shutil


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a high-density handnote cover prompt from a full article."
    )
    parser.add_argument("--article", required=True, help="Path to article markdown")
    parser.add_argument("--output", help="Output image path (PNG)")
    parser.add_argument("--prompt-out", help="Prompt markdown output path")
    parser.add_argument("--title", help="Override title text")
    parser.add_argument("--prompt-only", action="store_true", help="Only write prompt file")
    parser.add_argument("--session-id", help="Gemini session ID")
    parser.add_argument("--model", help="Gemini model id (optional)")
    args = parser.parse_args()

    article_path = Path(args.article).expanduser().resolve()
    if not article_path.exists():
        print(f"Article not found: {article_path}", file=sys.stderr)
        return 1

    skill_root = Path(__file__).resolve().parents[1]
    skills_root = skill_root.parent

    constraints_path = skill_root / "references" / "constraints.md"
    style_path = skills_root / "aki-style-library" / "references" / "styles" / "handnote.md"

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
    output_path = Path(args.output).expanduser().resolve() if args.output else (
        base_dir / "imgs" / "handnote-cover.png"
    )

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

    gemini_dir = skills_root / "baoyu-gemini-web"
    gemini_script = gemini_dir / "scripts" / "main.ts"
    if not gemini_script.exists():
        print(f"Gemini script not found: {gemini_script}", file=sys.stderr)
        return 1

    ensure_parent(output_path)

    bun_path = os.environ.get("BUN_PATH") or shutil.which("bun")
    if bun_path:
        cmd = [
            bun_path,
            str(gemini_script),
            "--promptfiles",
            str(prompt_out),
            "--image",
            str(output_path),
        ]
    else:
        cmd = [
            "npx",
            "-y",
            "bun",
            str(gemini_script),
            "--promptfiles",
            str(prompt_out),
            "--image",
            str(output_path),
        ]
    if args.session_id:
        cmd += ["--sessionId", args.session_id]
    if args.model:
        cmd += ["--model", args.model]

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=gemini_dir)
    if result.returncode != 0:
        return result.returncode

    print(f"Image generated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
