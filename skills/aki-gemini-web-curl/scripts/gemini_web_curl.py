#!/usr/bin/env python3
"""Gemini Web image generation via Chrome cookies + curl.

Uses curl --http1.1 for network requests because mixed proxy setups on this
machine are significantly more stable with curl than with bun/httpx/requests.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
APP_URL = "https://gemini.google.com/app"
GENERATE_URL = (
    "https://gemini.google.com/_/BardChatUi/data/"
    "assistant.lamda.BardFrontendService/StreamGenerate"
)
MODEL_HEADERS = {
    "gemini-3-pro": '[1,null,null,null,"9d8ca3786ebdfbea",null,null,0,[4]]',
    "gemini-2.5-pro": '[1,null,null,null,"4af6c7f5da75d65d",null,null,0,[4]]',
    "gemini-2.5-flash": '[1,null,null,null,"9ec249fc9ad08861",null,null,0,[4]]',
}
BACKEND_HINTS = ("Nano Banana 2", "Nano Banana Pro")


@dataclass
class Candidate:
    filename: str
    url: str
    mime: str
    width: int
    height: int
    bytes_size: int


@dataclass
class ResultMeta:
    output_path: str
    raw_path: str
    chat_model: str
    backend_hint: str | None
    candidate_url: str
    candidate_expected_width: int
    candidate_expected_height: int
    downloaded_width: int
    downloaded_height: int
    ratio_passed: bool


def log(msg: str) -> None:
    print(msg, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Gemini Web images via curl.")
    parser.add_argument("--prompt", help="Prompt text")
    parser.add_argument("--prompt-file", help="Path to a prompt file")
    parser.add_argument("--output", required=True, help="Final image output path")
    parser.add_argument("--chat-model", default="gemini-2.5-pro", choices=tuple(MODEL_HEADERS))
    parser.add_argument("--target-ratio", default="3:4", help="Target ratio like 3:4")
    parser.add_argument("--ratio-tolerance", type=float, default=0.08)
    parser.add_argument("--reroll", type=int, default=6)
    parser.add_argument("--proxy", default="", help="Optional proxy override such as socks5://127.0.0.1:7890")
    parser.add_argument("--raw-output", default="", help="Optional raw response output path")
    parser.add_argument("--meta-output", default="", help="Optional metadata output path")
    parser.add_argument("--cookie-json", default="", help="Optional existing cookie JSON file")
    parser.add_argument("--min-width", type=int, default=0)
    parser.add_argument("--min-height", type=int, default=0)
    return parser.parse_args()


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return args.prompt.strip()
    if args.prompt_file:
        return Path(args.prompt_file).read_text().strip()
    raise SystemExit("Missing --prompt or --prompt-file")


def parse_ratio(raw: str) -> tuple[float, bool]:
    left, right = raw.split(":", 1)
    a = float(left)
    b = float(right)
    return a / b, a < b


def build_env(proxy: str) -> dict[str, str]:
    env = os.environ.copy()
    if proxy:
        env["HTTP_PROXY"] = ""
        env["HTTPS_PROXY"] = ""
        env["NO_PROXY"] = ""
        env["ALL_PROXY"] = proxy
    return env


def run_curl(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["curl", "--http1.1", *args], capture_output=True, text=True, env=env)


def load_cookie_map(cookie_json: str = "") -> dict[str, str]:
    if cookie_json:
        raw = json.loads(Path(cookie_json).read_text())
        if isinstance(raw, dict) and raw.get("version") == 1 and isinstance(raw.get("cookieMap"), dict):
            return {k: v for k, v in raw["cookieMap"].items() if isinstance(v, str) and v}
        return {k: v for k, v in raw.items() if isinstance(v, str) and v}

    try:
        import browser_cookie3  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency is runtime only
        raise SystemExit(
            "Missing dependency: browser-cookie3. Install it with `pip install browser-cookie3`, "
            "or pass --cookie-json with an existing Gemini cookie export."
        ) from exc

    jar = browser_cookie3.chrome(domain_name="google.com")
    cookie_map: dict[str, str] = {}
    for cookie in jar:
        if not cookie.name or not cookie.value:
            continue
        cookie_map[cookie.name] = cookie.value
    required = ("__Secure-1PSID", "__Secure-1PSIDTS")
    missing = [name for name in required if name not in cookie_map]
    if missing:
        raise SystemExit(f"Missing required Gemini cookies: {', '.join(missing)}")
    return cookie_map


def build_seed_cookie(cookie_map: dict[str, str]) -> str:
    preferred = ["__Secure-1PSID", "__Secure-1PSIDTS", "NID"]
    parts = [f"{name}={cookie_map[name]}" for name in preferred if name in cookie_map]
    if not parts:
        raise SystemExit("No usable Gemini cookies found.")
    return "; ".join(parts)


def fetch_token(seed_cookie: str, env: dict[str, str]) -> tuple[str, Path]:
    jar = Path(tempfile.mkstemp(prefix="gemcurl_", suffix=".txt")[1])
    page = run_curl(
        [
            "-sSL",
            "--max-time",
            "45",
            "-c",
            str(jar),
            "-b",
            seed_cookie,
            "-H",
            f"user-agent: {USER_AGENT}",
            APP_URL,
        ],
        env,
    )
    if page.returncode != 0:
        raise RuntimeError(f"token page failed: rc={page.returncode} {page.stderr[:160].replace(chr(10), ' ')}")
    match = re.search(r'"(?:SNlM0e|thykhd)":"(.*?)"', page.stdout)
    if not match:
        raise RuntimeError("Gemini token not found on /app page.")
    return match.group(1), jar


def generate_raw(prompt: str, token: str, jar: Path, chat_model: str, env: dict[str, str]) -> str:
    f_req = json.dumps([None, json.dumps([[prompt], None, None], ensure_ascii=False)], ensure_ascii=False)
    response = run_curl(
        [
            "-sS",
            "--max-time",
            "210",
            "-X",
            "POST",
            GENERATE_URL,
            "-c",
            str(jar),
            "-b",
            str(jar),
            "-H",
            "content-type: application/x-www-form-urlencoded;charset=utf-8",
            "-H",
            "origin: https://gemini.google.com",
            "-H",
            "referer: https://gemini.google.com/",
            "-H",
            "x-same-domain: 1",
            "-H",
            f"user-agent: {USER_AGENT}",
            "-H",
            f"x-goog-ext-525001261-jspb: {MODEL_HEADERS[chat_model]}",
            "--data-urlencode",
            f"at={token}",
            "--data-urlencode",
            f"f.req={f_req}",
        ],
        env,
    )
    if response.returncode != 0:
        raise RuntimeError(
            f"generate failed: rc={response.returncode} {response.stderr[:160].replace(chr(10), ' ')}"
        )
    return response.stdout


def detect_backend_hint(raw_text: str) -> str | None:
    for hint in BACKEND_HINTS:
        if hint in raw_text:
            return hint
    return None


def parse_candidates(raw_text: str) -> list[Candidate]:
    pattern = re.compile(
        r'"(?P<filename>[^"]+\.(?:png|jpe?g|webp))",'
        r'"(?P<url>https://lh3\.googleusercontent\.com/gg-dl/[^"]+)"'
        r'.*?'
        r'"(?P<mime>image/(?:png|jpeg|webp))"'
        r'.*?'
        r'\[(?P<width>\d+),(?P<height>\d+),(?P<size>\d+)\]',
        re.DOTALL,
    )
    out: list[Candidate] = []
    seen: set[str] = set()
    for match in pattern.finditer(raw_text):
        url = match.group("url").rstrip("/").split("\\")[0]
        if url in seen:
            continue
        seen.add(url)
        out.append(
            Candidate(
                filename=match.group("filename"),
                url=url,
                mime=match.group("mime"),
                width=int(match.group("width")),
                height=int(match.group("height")),
                bytes_size=int(match.group("size")),
            )
        )
    return out


def image_dims(path: Path) -> tuple[int, int]:
    proc = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)], capture_output=True, text=True)
    match_w = re.search(r"pixelWidth: (\d+)", proc.stdout)
    match_h = re.search(r"pixelHeight: (\d+)", proc.stdout)
    return (int(match_w.group(1)) if match_w else 0, int(match_h.group(1)) if match_h else 0)


def ratio_ok(width: int, height: int, target_ratio: float, expect_portrait: bool, tolerance: float) -> bool:
    if width <= 0 or height <= 0:
        return False
    if expect_portrait and not (height > width):
        return False
    actual = width / height
    return abs(actual - target_ratio) <= tolerance


def download_candidate(
    candidate: Candidate,
    jar: Path,
    out_base: Path,
    env: dict[str, str],
) -> tuple[Path | None, int, int]:
    variants = [candidate.url + "=s4096", candidate.url + "=s2048", candidate.url]
    best_path: Path | None = None
    best_dims = (0, 0)
    for target in variants:
        temp_path = Path(tempfile.mkstemp(prefix=out_base.name + "_", suffix=".bin")[1])
        response = run_curl(
            [
                "-sSL",
                "--max-time",
                "90",
                "-c",
                str(jar),
                "-b",
                str(jar),
                "-H",
                f"user-agent: {USER_AGENT}",
                "-o",
                str(temp_path),
                target,
            ],
            env,
        )
        if response.returncode != 0:
            temp_path.unlink(missing_ok=True)
            continue
        mime = subprocess.run(["file", "--mime-type", "-b", str(temp_path)], capture_output=True, text=True).stdout.strip()
        if not mime.startswith("image/"):
            temp_path.unlink(missing_ok=True)
            continue
        width, height = image_dims(temp_path)
        if width * height > best_dims[0] * best_dims[1]:
            ext = {candidate.mime: Path(candidate.filename).suffix}.get(candidate.mime, Path(candidate.filename).suffix or ".png")
            final_path = out_base.with_suffix(ext)
            shutil.move(str(temp_path), str(final_path))
            if best_path and best_path.exists():
                best_path.unlink(missing_ok=True)
            best_path = final_path
            best_dims = (width, height)
        else:
            temp_path.unlink(missing_ok=True)
    return best_path, best_dims[0], best_dims[1]


def choose_candidate(candidates: Iterable[Candidate]) -> list[Candidate]:
    return sorted(candidates, key=lambda item: item.width * item.height, reverse=True)


def main() -> int:
    args = parse_args()
    prompt = read_prompt(args)
    target_ratio, expect_portrait = parse_ratio(args.target_ratio)
    env = build_env(args.proxy)
    cookie_map = load_cookie_map(args.cookie_json)
    seed_cookie = build_seed_cookie(cookie_map)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = Path(args.raw_output) if args.raw_output else output_path.with_suffix(".raw.txt")
    meta_path = Path(args.meta_output) if args.meta_output else output_path.with_suffix(".meta.json")

    last_error = None
    for attempt in range(1, args.reroll + 1):
        log(f"[gemini-web-curl] attempt {attempt}/{args.reroll}")
        try:
            token, jar = fetch_token(seed_cookie, env)
            raw_text = generate_raw(prompt, token, jar, args.chat_model, env)
            raw_attempt_path = raw_path if args.reroll == 1 else raw_path.with_name(f"{raw_path.stem}-{attempt}{raw_path.suffix}")
            raw_attempt_path.write_text(raw_text)

            candidates = choose_candidate(parse_candidates(raw_text))
            if not candidates:
                raise RuntimeError("no generated image candidates found in Gemini raw response")

            backend_hint = detect_backend_hint(raw_text)
            for index, candidate in enumerate(candidates, start=1):
                final_base = output_path if index == 1 else output_path.with_name(f"{output_path.stem}-{index}")
                downloaded_path, dw, dh = download_candidate(candidate, jar, final_base, env)
                if not downloaded_path:
                    continue
                width_ok = dw >= max(candidate.width, args.min_width)
                height_ok = dh >= max(candidate.height, args.min_height)
                passed_ratio = ratio_ok(dw, dh, target_ratio, expect_portrait, args.ratio_tolerance)
                meta = ResultMeta(
                    output_path=str(downloaded_path),
                    raw_path=str(raw_attempt_path),
                    chat_model=args.chat_model,
                    backend_hint=backend_hint,
                    candidate_url=candidate.url,
                    candidate_expected_width=candidate.width,
                    candidate_expected_height=candidate.height,
                    downloaded_width=dw,
                    downloaded_height=dh,
                    ratio_passed=passed_ratio,
                )
                meta_attempt_path = meta_path if args.reroll == 1 else meta_path.with_name(f"{meta_path.stem}-{attempt}{meta_path.suffix}")
                meta_attempt_path.write_text(json.dumps(asdict(meta), ensure_ascii=False, indent=2) + "\n")
                log(
                    f"[gemini-web-curl] candidate {index}: expected={candidate.width}x{candidate.height} "
                    f"downloaded={dw}x{dh} ratio_ok={passed_ratio} backend={backend_hint or 'unknown'}"
                )
                if width_ok and height_ok and passed_ratio:
                    if downloaded_path != output_path:
                        shutil.copyfile(downloaded_path, output_path.with_suffix(downloaded_path.suffix))
                    print(str(downloaded_path))
                    return 0
            last_error = "no candidate passed ratio/dimension validation"
        except Exception as exc:  # pragma: no cover - runtime/network path
            last_error = str(exc)
            log(f"[gemini-web-curl] {last_error}")
        time.sleep(2 + random.random())

    print(f"[gemini-web-curl] failed: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
