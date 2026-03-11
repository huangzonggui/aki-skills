#!/usr/bin/env python3
"""
Article/image/script to JianYing draft pipeline.

Workflow:
1) Build a scratch draft with images + subtitles (no template clone)
2) Generate TTS audio
3) Inject a compatibility-first local audio track into draft JSON
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, List
from urllib import error as urlerror
from urllib import request as urlrequest

from pipeline_config import load_pipeline_config
from subtitle_engine import generate_aligned_srt

DEFAULT_JY_PIPELINE = Path(
    "/Users/aki/.agents/skills/jianying-editor/scripts/article_assets_to_video_pipeline.py"
)
DEFAULT_TRANSFORM_TS = Path(
    "/Users/aki/Development/code/aki-skills/skills/aki-article-transformer/scripts/transform.ts"
)
DEFAULT_SCRIPT_TO_SRT = Path(
    "/Users/aki/.agents/skills/jianying-editor/scripts/script_to_srt.py"
)
DEFAULT_SCRATCH_BUILDER = Path(
    "/Users/aki/.agents/skills/jianying-editor/scripts/jy_from_scratch_builder.py"
)

_CFG = load_pipeline_config()
DEFAULT_PROJECTS_ROOT = _CFG.jy_projects_root
DEFAULT_KEYS_ENV_FILE = _CFG.ai_keys_env_path

VOICE_STYLE_MAP = {
    "daily-relaxed-male": "zh-CN-YunxiNeural",
    "daily-pro-male": "zh-CN-YunyangNeural",
    "daily-energetic-male": "zh-CN-YunjianNeural",
    "daily-relaxed-female": "zh-CN-XiaoxiaoNeural",
}

MINIMAX_STYLE_MAP = {
    "daily-relaxed-male": "Chinese (Mandarin)_Gentleman",
    "daily-pro-male": "Chinese (Mandarin)_Male_Announcer",
    "daily-energetic-male": "Chinese (Mandarin)_Southern_Young_Man",
    "daily-relaxed-female": "Chinese (Mandarin)_Female_Announcer",
}

# "日常松弛男" is a common JianYing voice naming habit; map it to the closest
# known MiniMax system voice id.
MINIMAX_NAME_ALIAS = {
    "日常松弛男": "Chinese (Mandarin)_Gentleman",
}

NON_SPOKEN_TITLE_RE = re.compile(
    r"^(?:视频)?口播(?:脚本|稿)(?:最终版|定稿|完整版|初稿)?$",
    re.IGNORECASE,
)


def _is_non_spoken_title_line(text: str) -> bool:
    # Skip common script title lines, e.g. "视频口播脚本（最终版）".
    t = re.sub(r"\s+", "", text or "").strip("：:;；-—")
    if not t:
        return False
    plain = re.sub(r"[（(][^）)]*[）)]", "", t)
    if NON_SPOKEN_TITLE_RE.match(plain):
        return True
    if ("口播脚本" in plain or "口播稿" in plain) and len(plain) <= 20:
        return True
    return False


def redact_cmd(cmd: List[str]) -> str:
    sanitized: List[str] = []
    for i, part in enumerate(cmd):
        if part.startswith("Authorization: Bearer "):
            sanitized.append("Authorization: Bearer ***")
            continue
        if i > 0 and cmd[i - 1].lower() == "authorization:":
            sanitized.append("Bearer ***")
            continue
        if "Bearer sk-" in part:
            sanitized.append(part.split("Bearer ")[0] + "Bearer ***")
            continue
        sanitized.append(part)
    return " ".join(sanitized)


def run(cmd: List[str]) -> None:
    print("▶", redact_cmd(cmd))
    subprocess.run(cmd, check=True)


def run_capture(cmd: List[str]) -> str:
    print("▶", redact_cmd(cmd))
    cp = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return cp.stdout.strip()


def sanitize_siliconflow_custom_name(name: str) -> str:
    # SiliconFlow accepts only letters, digits, "_" and "-"
    v = re.sub(r"[^A-Za-z0-9_-]+", "_", name or "")
    v = re.sub(r"_+", "_", v).strip("_-")
    if not v:
        v = "voice_ref"
    return v[:64]


def parse_durations(raw: str | None) -> List[float]:
    if not raw:
        return []
    vals: List[float] = []
    for x in raw.split(","):
        t = x.strip()
        if not t:
            continue
        vals.append(float(t))
    return vals


def scale_durations_to_total(durations: List[float], total: float) -> List[float]:
    if not durations:
        return durations
    s = sum(durations)
    if s <= 0:
        return durations
    k = total / s
    return [max(0.05, d * k) for d in durations]


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def maybe_write_report(report_path: str, report: dict[str, Any]) -> None:
    if not report_path:
        return
    p = Path(report_path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_assets(args: argparse.Namespace) -> List[Path]:
    if args.assets:
        assets = [Path(x.strip()).expanduser().resolve() for x in args.assets.split(",") if x.strip()]
    else:
        if not args.assets_dir:
            raise ValueError("either --assets or --assets-dir is required")
        base = Path(args.assets_dir).expanduser().resolve()
        names = ["0-cover.png", "1.png", "2.png", "3.png"]
        preferred = [base / name for name in names if (base / name).exists()]
        if preferred:
            assets = preferred
        else:
            images: List[Path] = []
            for pat in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"):
                images.extend(sorted(base.glob(pat)))
                images.extend(sorted(base.glob(pat.upper())))
            # de-dup with stable ordering by filename
            unique = {}
            for p in images:
                unique[str(p.resolve())] = p.resolve()
            assets = sorted(unique.values(), key=lambda p: p.name.lower())

    if not assets:
        raise ValueError("no assets provided")

    for asset in assets:
        if not asset.exists():
            raise FileNotFoundError(f"asset missing: {asset}")

    return assets


def _normalize_script_lines_for_tts(raw_text: str, preserve_numbering: bool = True) -> List[str]:
    lines: List[str] = []
    for line in raw_text.splitlines():
        s = line.strip()
        if not s:
            continue
        # Remove markdown heading marks but keep heading content.
        s = re.sub(r"^#{1,6}\s*", "", s)
        # Remove block quote prefix.
        s = re.sub(r"^>\s*", "", s)
        # Remove markdown emphasis and inline code markers.
        s = s.replace("**", "").replace("__", "").replace("`", "")
        # Convert markdown links to visible text only.
        s = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", s)
        # Drop pure metadata lines.
        if re.match(r"^时长\s*[:：]", s):
            continue
        if _is_non_spoken_title_line(s):
            continue

        m_num = re.match(r"^(\d+)[\.\)、]\s*(.+)$", s)
        if m_num:
            idx, body = m_num.group(1), m_num.group(2).strip()
            if preserve_numbering:
                s = f"{idx}. {body}"
            else:
                s = body
        else:
            s = re.sub(r"^[-*]\s*", "", s)

        s = re.sub(r"\s+", " ", s).strip()
        # Keep sentence rhythm stable for TTS.
        if s and s[-1] not in "。！？!?；;：:":
            s += "。"
        lines.append(s)
    return lines


def clean_script_text(script_path: Path, strict_verbatim: bool = False) -> str:
    text = script_path.read_text(encoding="utf-8")
    if strict_verbatim:
        text = text.strip()
        if not text:
            raise ValueError(f"script is empty: {script_path}")
        return text
    lines = _normalize_script_lines_for_tts(text, preserve_numbering=True)
    text = "\n".join(lines).strip()
    if not text:
        raise ValueError(f"script is empty after cleanup: {script_path}")
    return text


def suggest_durations_from_script(script_text: str, asset_count: int, total_duration: float) -> List[float]:
    if asset_count <= 1 or total_duration <= 0:
        return []
    lines = [x.strip() for x in script_text.splitlines() if x.strip()]
    if not lines:
        return []

    intro: List[str] = []
    points: List[str] = []
    tail: List[str] = []
    in_points = False
    for ln in lines:
        if re.match(r"^(第\\s*\\d+\\s*点|\\d+[\\.\\)、])", ln):
            points.append(ln)
            in_points = True
            continue
        if not in_points:
            intro.append(ln)
        else:
            tail.append(ln)

    if not points:
        # No explicit numbered structure -> even split.
        return [total_duration / asset_count] * asset_count

    buckets: List[List[str]] = [[] for _ in range(asset_count)]
    if intro:
        buckets[0].extend(intro)
    else:
        buckets[0].append(points[0])
        points = points[1:]

    if asset_count > 1:
        for i, p in enumerate(points):
            target = 1 + (i % (asset_count - 1))
            buckets[target].append(p)
    if tail:
        buckets[-1].extend(tail)

    weights: List[float] = []
    for b in buckets:
        chars = sum(len(re.sub(r"\s+", "", x)) for x in b)
        weights.append(float(max(20, chars)))
    s = sum(weights)
    if s <= 0:
        return [total_duration / asset_count] * asset_count
    out = [max(0.5, total_duration * (w / s)) for w in weights]
    return scale_durations_to_total(out, total_duration)


def count_speakable_chars(text: str) -> int:
    # Count Chinese chars + letters + numbers as CPM denominator.
    return len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))


def speed_to_rate(speed_ratio: float) -> str:
    delta = int(round((speed_ratio - 1.0) * 100))
    return f"{delta:+d}%"


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, value = s.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def minimax_post_json(api_base: str, endpoint: str, api_key: str, payload: dict) -> dict:
    url = f"{api_base.rstrip('/')}{endpoint}"
    req = urlrequest.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            body = str(e)
        raise RuntimeError(f"MiniMax HTTP {e.code}: {body[:500]}") from e
    except Exception as e:
        raise RuntimeError(f"MiniMax request failed: {e}") from e


def siliconflow_post_multipart_json(
    api_base: str,
    endpoint: str,
    api_key: str,
    form_args: List[str],
) -> dict:
    cmd = [
        "curl",
        "-sS",
        "--location",
        f"{api_base.rstrip('/')}{endpoint}",
        "-H",
        f"Authorization: Bearer {api_key}",
    ]
    for item in form_args:
        cmd.extend(["-F", item])
    raw = run_capture(cmd)
    try:
        data = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"SiliconFlow invalid JSON response: {raw[:500]}") from e

    if isinstance(data, dict) and data.get("code") not in (None, 200, 0):
        raise RuntimeError(
            f"SiliconFlow API error {data.get('code')}: {data.get('message') or data.get('msg')}"
        )
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"SiliconFlow API error: {data.get('error')}")
    return data


def siliconflow_transcribe_audio(
    api_base: str,
    api_key: str,
    audio_path: Path,
    asr_model: str,
) -> str:
    data = siliconflow_post_multipart_json(
        api_base=api_base,
        endpoint="/v1/audio/transcriptions",
        api_key=api_key,
        form_args=[
            f"file=@{audio_path}",
            f"model={asr_model}",
        ],
    )
    text = ""
    if isinstance(data, dict):
        text = (data.get("text") or "").strip()
    if not text:
        raise RuntimeError(f"SiliconFlow transcription returned empty text: {data}")
    return text


def siliconflow_upload_voice(
    api_base: str,
    api_key: str,
    model: str,
    ref_audio: Path,
    ref_text: str,
    custom_name: str,
) -> str:
    safe_name = sanitize_siliconflow_custom_name(custom_name)
    data = siliconflow_post_multipart_json(
        api_base=api_base,
        endpoint="/v1/uploads/audio/voice",
        api_key=api_key,
        form_args=[
            f"file=@{ref_audio}",
            f"model={model}",
            f"customName={safe_name}",
            f"text={ref_text}",
        ],
    )
    uri = ""
    if isinstance(data, dict):
        uri = str((data.get("uri") or "")).strip()
    if not uri:
        raise RuntimeError(f"SiliconFlow upload voice returned empty uri: {data}")
    return uri


def prepare_script(
    article: Path | None,
    script_file: Path | None,
    transform_ts: Path,
    new_name: str,
    workdir: Path,
    duration_hint: float,
) -> Path:
    out_script = workdir / f"{new_name}_口播稿.md"
    if script_file:
        out_script.write_text(script_file.read_text(encoding="utf-8"), encoding="utf-8")
        return out_script
    if not article:
        raise ValueError("either script_file or article is required")
    run(
        [
            "npx",
            "-y",
            "bun",
            str(transform_ts),
            str(article),
            "--mode",
            "script",
            "--duration",
            str(int(round(duration_hint))),
            "--output",
            str(out_script),
        ]
    )
    return out_script


def maybe_run_script_editor(
    script_path: Path,
    workdir: Path,
    editor_cmd: str,
    timeout_sec: int,
) -> Path:
    cmd_tpl = (editor_cmd or "").strip()
    if not cmd_tpl:
        return script_path

    edited_script = script_path.with_name(f"{script_path.stem}__edited{script_path.suffix}")
    q_input = shlex.quote(str(script_path))
    q_output = shlex.quote(str(edited_script))
    q_workdir = shlex.quote(str(workdir))

    cmd = (
        cmd_tpl.replace("{input}", q_input)
        .replace("{output}", q_output)
        .replace("{workdir}", q_workdir)
    )
    if "{input}" not in cmd_tpl and "{output}" not in cmd_tpl:
        cmd = f"{cmd} {q_input} {q_output}"

    print(f"▶ script-editor {cmd}")
    subprocess.run(cmd, shell=True, check=True, timeout=max(1, int(timeout_sec)))

    if edited_script.exists():
        txt = edited_script.read_text(encoding="utf-8", errors="ignore").strip()
        if txt:
            return edited_script

    txt_inplace = script_path.read_text(encoding="utf-8", errors="ignore").strip()
    if txt_inplace:
        return script_path
    raise RuntimeError("script editor produced empty script")


def generate_srt_heuristic(script_to_srt: Path, script: Path, output_srt: Path, duration: float) -> None:
    run(
        [
            "python3",
            str(script_to_srt),
            "--script",
            str(script),
            "--output",
            str(output_srt),
            "--duration",
            str(duration),
        ]
    )


def generate_srt_whisper(audio_path: Path, output_srt: Path, model: str, language: str) -> None:
    whisper_bin = shutil.which("whisper")
    if not whisper_bin:
        raise RuntimeError("whisper command not found in PATH")
    with tempfile.TemporaryDirectory(prefix="agi-whisper-") as tmpdir:
        out_dir = Path(tmpdir)
        run(
            [
                whisper_bin,
                str(audio_path),
                "--model",
                model,
                "--task",
                "transcribe",
                "--language",
                language,
                "--output_dir",
                str(out_dir),
                "--output_format",
                "srt",
                "--verbose",
                "False",
                "--fp16",
                "False",
            ]
        )
        src = out_dir / f"{audio_path.stem}.srt"
        if not src.exists():
            raise RuntimeError(f"whisper output srt missing: {src}")
        output_srt.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _parse_srt_blocks(srt_text: str) -> List[dict[str, Any]]:
    blocks: List[dict[str, Any]] = []
    raw_blocks = re.split(r"\n\s*\n", srt_text.strip(), flags=re.MULTILINE)
    for raw in raw_blocks:
        lines = [x.rstrip("\r") for x in raw.splitlines() if x.strip()]
        if len(lines) < 2 or "-->" not in lines[1]:
            continue
        timeline = lines[1].strip()
        text = "\n".join(lines[2:]).strip()
        blocks.append({"timeline": timeline, "text": text})
    return blocks


def _format_srt_blocks(blocks: List[dict[str, Any]]) -> str:
    out: List[str] = []
    for i, b in enumerate(blocks, 1):
        out.append(str(i))
        out.append(b["timeline"])
        out.append((b.get("text") or "").strip() or " ")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _srt_time_to_seconds(ts: str) -> float:
    # format: HH:MM:SS,mmm
    hms, ms = ts.strip().split(",", 1)
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _timeline_duration_sec(timeline: str) -> float:
    a, b = [x.strip() for x in timeline.split("-->")]
    return max(0.01, _srt_time_to_seconds(b) - _srt_time_to_seconds(a))


def rewrite_srt_text_with_script(srt_path: Path, script_text: str) -> None:
    src = srt_path.read_text(encoding="utf-8", errors="ignore")
    blocks = _parse_srt_blocks(src)
    if not blocks:
        return

    text = re.sub(r"\s+", "", script_text or "")
    if not text:
        return

    # Use ASR segment text lengths as weights first (better sync than pure duration split).
    asr_weights: List[int] = []
    for b in blocks:
        n = len(re.sub(r"\s+", "", b.get("text", "")))
        asr_weights.append(max(1, n))
    total_weight = sum(asr_weights)
    durations = [_timeline_duration_sec(b["timeline"]) for b in blocks]
    total_dur = max(1e-9, sum(durations))
    total_chars = len(text)
    cursor = 0
    rewritten: List[str] = []

    def _snap_cut(preferred: int, left: int, right: int) -> int:
        # Try nearby punctuation to keep phrase boundaries natural.
        lo = max(left + 1, preferred - 8)
        hi = min(right, preferred + 8)
        punct = "，。！？；、,.!?;：:"
        for j in range(preferred, hi):
            if text[j] in punct:
                return j + 1
        for j in range(preferred - 1, lo - 1, -1):
            if text[j] in punct:
                return j + 1
        return max(left + 1, min(right, preferred))

    for i, dur in enumerate(durations):
        remain_blocks = len(durations) - i
        remain_chars = total_chars - cursor
        if remain_blocks <= 1:
            seg = text[cursor:]
            rewritten.append(seg)
            cursor = total_chars
            continue

        if total_weight > 0:
            want = max(1, int(round(total_chars * (asr_weights[i] / total_weight))))
        else:
            want = max(1, int(round(total_chars * (dur / total_dur))))
        want = min(want, max(1, remain_chars - (remain_blocks - 1)))
        right = min(total_chars, cursor + want)
        cut = _snap_cut(preferred=right, left=cursor, right=total_chars)
        seg = text[cursor:cut]
        if not seg:
            seg = text[cursor : min(total_chars, cursor + 1)]
            cut = cursor + len(seg)
        rewritten.append(seg)
        cursor = cut

    for i, b in enumerate(blocks):
        b["text"] = rewritten[i] if i < len(rewritten) else ""
    srt_path.write_text(_format_srt_blocks(blocks), encoding="utf-8")


def apply_atempo_speed(input_m4a: Path, output_m4a: Path, speed_ratio: float) -> None:
    if abs(speed_ratio - 1.0) < 1e-3:
        shutil.copy2(input_m4a, output_m4a)
        return

    r = speed_ratio
    factors: List[float] = []
    while r > 2.0:
        factors.append(2.0)
        r /= 2.0
    while r < 0.5:
        factors.append(0.5)
        r /= 0.5
    factors.append(r)
    chain = ",".join(f"atempo={x:.6f}" for x in factors)
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_m4a),
            "-filter:a",
            chain,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(output_m4a),
        ]
    )


def build_scratch_draft_from_srt(
    scratch_builder: Path,
    projects_root: Path,
    new_name: str,
    assets: List[Path],
    srt_path: Path,
    total_duration: float,
    durations: List[float],
    transition_primary: str,
    transition_fallback: str,
    transition_duration: str,
    subtitle_font: str,
) -> str:
    base_cmd = [
        "python3",
        str(scratch_builder),
        "--projects-root",
        str(projects_root),
        "--new-name",
        new_name,
        "--assets",
        ",".join(str(x) for x in assets),
        "--srt",
        str(srt_path),
        "--subtitle-font",
        subtitle_font,
    ]
    if durations:
        base_cmd.extend(["--durations", ",".join(f"{x:.6f}" for x in durations)])
    else:
        base_cmd.extend(["--total-duration", str(total_duration)])

    def _run_with_transition(transition_name: str) -> None:
        cmd = list(base_cmd)
        cmd.extend(["--transition", transition_name, "--transition-duration", transition_duration])
        run(cmd)

    primary = (transition_primary or "").strip() or "翻页"
    fallback = (transition_fallback or "").strip() or primary
    try:
        _run_with_transition(primary)
        return primary
    except Exception as e:
        if primary == fallback:
            raise RuntimeError(f"scratch builder failed with transition={primary}: {e}") from e
        print(f"⚠️ transition '{primary}' failed ({e}); fallback to '{fallback}'")
        _run_with_transition(fallback)
        return fallback


def synthesize_audio_edge(
    text: str,
    voice: str,
    speed_ratio: float,
    out_m4a: Path,
) -> None:
    out_m4a.parent.mkdir(parents=True, exist_ok=True)
    rate = speed_to_rate(speed_ratio)

    with tempfile.TemporaryDirectory(prefix="agi-tts-") as tmpdir:
        tmp = Path(tmpdir)
        txt = tmp / "tts_input.txt"
        mp3 = tmp / "tts.mp3"

        txt.write_text(text + "\n", encoding="utf-8")

        run(
            [
                "edge-tts",
                "--voice",
                voice,
                "--rate",
                rate,
                "--file",
                str(txt),
                "--write-media",
                str(mp3),
            ]
        )

        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(mp3),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-ac",
                "2",
                str(out_m4a),
            ]
        )


def resolve_minimax_voice_id(
    api_base: str,
    api_key: str,
    voice_style: str,
    voice_id: str | None,
    voice_name: str | None,
) -> str:
    if voice_id:
        return voice_id

    data = minimax_post_json(
        api_base=api_base,
        endpoint="/v1/get_voice",
        api_key=api_key,
        payload={"voice_type": "all"},
    )
    base = data.get("base_resp", {})
    if int(base.get("status_code", -1)) != 0:
        raise RuntimeError(
            f"MiniMax get_voice failed: {base.get('status_code')} {base.get('status_msg')}"
        )

    all_voices = []
    for key in ("system_voice", "voice_cloning", "voice_generation"):
        all_voices.extend(data.get(key, []) or [])

    # exact name / id match first
    if voice_name:
        for v in all_voices:
            if (v.get("voice_name") or "").strip() == voice_name:
                return (v.get("voice_id") or "").strip()
            if (v.get("voice_id") or "").strip() == voice_name:
                return (v.get("voice_id") or "").strip()

        alias_id = MINIMAX_NAME_ALIAS.get(voice_name)
        if alias_id:
            return alias_id

    # style fallback
    style_id = MINIMAX_STYLE_MAP[voice_style]
    return style_id


def synthesize_audio_minimax(
    text: str,
    api_base: str,
    api_key: str,
    model: str,
    voice_id: str,
    speed_ratio: float,
    out_m4a: Path,
) -> None:
    out_m4a.parent.mkdir(parents=True, exist_ok=True)

    data = minimax_post_json(
        api_base=api_base,
        endpoint="/v1/t2a_v2",
        api_key=api_key,
        payload={
            "model": model,
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": voice_id,
                "speed": speed_ratio,
                "vol": 1,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
        },
    )

    base = data.get("base_resp", {})
    code = int(base.get("status_code", -1))
    if code != 0:
        msg = base.get("status_msg") or "unknown error"
        raise RuntimeError(f"MiniMax TTS failed: {code} {msg}")

    audio_hex = (data.get("data") or {}).get("audio")
    if not audio_hex:
        raise RuntimeError("MiniMax TTS returned empty audio payload")

    with tempfile.TemporaryDirectory(prefix="agi-minimax-tts-") as tmpdir:
        tmp = Path(tmpdir)
        mp3 = tmp / "tts.mp3"
        try:
            mp3.write_bytes(binascii.unhexlify(audio_hex))
        except Exception as e:
            raise RuntimeError(f"failed to decode MiniMax hex audio: {e}") from e

        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(mp3),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-ac",
                "2",
                str(out_m4a),
            ]
        )


def synthesize_audio_siliconflow(
    text: str,
    api_base: str,
    api_key: str,
    model: str,
    voice_uri: str,
    speed_ratio: float,
    out_m4a: Path,
) -> None:
    out_m4a.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "model": model,
        "input": text,
        "voice": voice_uri,
        "response_format": "mp3",
        "speed": speed_ratio,
    }
    req = urlrequest.Request(
        f"{api_base.rstrip('/')}/v1/audio/speech",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urlrequest.urlopen(req, timeout=180) as resp:
            content_type = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read()
    except urlerror.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            body = str(e)
        raise RuntimeError(f"SiliconFlow HTTP {e.code}: {body[:500]}") from e
    except Exception as e:
        raise RuntimeError(f"SiliconFlow request failed: {e}") from e

    if "application/json" in content_type:
        msg = raw.decode("utf-8", errors="ignore")
        raise RuntimeError(f"SiliconFlow speech returned JSON instead of audio: {msg[:500]}")

    with tempfile.TemporaryDirectory(prefix="agi-sf-tts-") as tmpdir:
        tmp = Path(tmpdir)
        mp3 = tmp / "tts.mp3"
        mp3.write_bytes(raw)
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(mp3),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-ac",
                "2",
                str(out_m4a),
            ]
        )


def probe_duration_us(audio_path: Path) -> int:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nk=1:nw=1",
            str(audio_path),
        ],
        text=True,
    ).strip()
    sec = float(out)
    return max(1, int(round(sec * 1_000_000)))


def patch_draft_audio(
    projects_root: Path,
    draft_name: str,
    audio_path: Path,
    target_duration_sec: float,
    clear_audio_effects: bool,
) -> None:
    draft_dir = projects_root / draft_name
    content_path = draft_dir / "draft_content.json"
    if not content_path.exists():
        raise FileNotFoundError(f"draft content not found: {content_path}")

    data = json.loads(content_path.read_text(encoding="utf-8"))
    target_us = int(round(target_duration_sec * 1_000_000))
    source_us = min(probe_duration_us(audio_path), target_us)

    materials = data.setdefault("materials", {})
    audios = materials.setdefault("audios", [])

    if audios:
        audio_item = audios[0]
        audios[:] = [audio_item]
        material_id = audio_item.get("id") or uuid.uuid4().hex
    else:
        material_id = uuid.uuid4().hex
        audio_item = {"id": material_id}
        audios.append(audio_item)

    audio_item["id"] = material_id
    audio_item["path"] = str(audio_path)
    audio_item["type"] = "extract_music"
    audio_item["duration"] = source_us
    audio_item["name"] = audio_path.name
    audio_item["material_name"] = audio_path.name
    audio_item["local_material_id"] = ""
    audio_item["music_id"] = ""
    audio_item["check_flag"] = 1
    audio_item["source_platform"] = 0
    audio_item["category_name"] = audio_item.get("category_name") or "local"
    audio_item["category_id"] = audio_item.get("category_id") or ""
    audio_item["copyright_limit_type"] = audio_item.get("copyright_limit_type") or "none"
    audio_item["wave_points"] = audio_item.get("wave_points") or []

    if clear_audio_effects:
        materials["audio_effects"] = []

    tracks = data.setdefault("tracks", [])
    audio_tracks = [t for t in tracks if t.get("type") == "audio"]
    if not audio_tracks:
        audio_track = {
            "attribute": 0,
            "flag": 0,
            "id": str(uuid.uuid4()).upper(),
            "is_default_name": False,
            "name": "AudioTrack",
            "segments": [],
            "type": "audio",
        }
        tracks.append(audio_track)
        audio_tracks = [audio_track]

    primary = audio_tracks[0]
    primary["flag"] = 0
    primary["name"] = primary.get("name") or "AudioTrack"
    primary["segments"] = [
        {
            "id": uuid.uuid4().hex,
            "material_id": material_id,
            "target_timerange": {"start": 0, "duration": target_us},
            "source_timerange": {"start": 0, "duration": source_us},
            "volume": 1.0,
            "speed": 1,
            "extra_material_refs": [],
            "visible": True,
            "track_attribute": 0,
        }
    ]

    for rest in audio_tracks[1:]:
        rest["segments"] = []

    data["duration"] = max(int(data.get("duration", 0) or 0), target_us)

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    content_path.write_text(payload, encoding="utf-8")
    (draft_dir / "draft_info.json").write_text(payload, encoding="utf-8")
    (draft_dir / "draft_info.json.bak").write_text(payload, encoding="utf-8")

    root_meta = projects_root / "root_meta_info.json"
    if root_meta.exists():
        rm = json.loads(root_meta.read_text(encoding="utf-8"))
        stores = rm.get("all_draft_store", [])
        stores = [x for x in stores if x.get("draft_name") != draft_name]
        entry = stores[0].copy() if stores else {}
        now = int(time.time() * 1_000_000)
        entry["draft_name"] = draft_name
        entry["draft_fold_path"] = str(draft_dir)
        entry["draft_root_path"] = str(projects_root)
        entry["draft_json_file"] = str(draft_dir / "draft_info.json")
        cover_jpg = draft_dir / "draft_cover.jpg"
        cover_png = draft_dir / "draft_cover.png"
        entry["draft_cover"] = str(cover_jpg if cover_jpg.exists() else cover_png)
        entry["tm_draft_create"] = now
        entry["tm_draft_modified"] = now
        entry["tm_duration"] = target_us
        entry["draft_id"] = uuid.uuid4().hex.upper()
        stores.insert(0, entry)
        rm["all_draft_store"] = stores
        rm["draft_ids"] = len(stores)
        root_meta.write_text(
            json.dumps(rm, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )



def main() -> None:
    parser = argparse.ArgumentParser(description="Build JianYing draft from article/images/script")
    parser.add_argument("--article", help="article markdown path")
    parser.add_argument("--script-file", help="existing voice script path")
    parser.add_argument("--assets", help="comma-separated absolute asset paths")
    parser.add_argument("--assets-dir", help="asset directory; default picks 0-cover.png,1.png,2.png,3.png")
    parser.add_argument("--new-name", required=True, help="new JianYing draft name")
    parser.add_argument("--duration", type=float, default=30.0, help="script target seconds (generation hint)")
    parser.add_argument("--durations", default=None, help="optional segment durations")
    parser.add_argument("--projects-root", default=str(DEFAULT_PROJECTS_ROOT))
    parser.add_argument("--workdir", default=".")
    parser.add_argument("--jy-pipeline", default=str(DEFAULT_JY_PIPELINE), help="kept for backward compatibility")
    parser.add_argument("--transform-ts", default=str(DEFAULT_TRANSFORM_TS))
    parser.add_argument("--script-to-srt", default=str(DEFAULT_SCRIPT_TO_SRT))
    parser.add_argument("--scratch-builder", default=str(DEFAULT_SCRATCH_BUILDER))
    parser.add_argument("--tts-provider", choices=["auto", "edge", "minimax", "siliconflow"], default="edge")
    parser.add_argument("--voice-style", default="daily-relaxed-male", choices=sorted(VOICE_STYLE_MAP.keys()))
    parser.add_argument("--edge-voice", help="override edge-tts voice")
    parser.add_argument("--voice-speed", type=float, default=1.0, help="tts speed ratio")
    parser.add_argument(
        "--script-format",
        choices=["auto", "verbatim"],
        default="auto",
        help="auto: normalize raw script into oral-friendly lines; verbatim: use text as-is",
    )
    parser.add_argument(
        "--script-editor-cmd",
        default="",
        help=(
            "optional external script editor command; supports placeholders "
            "{input} {output} {workdir}"
        ),
    )
    parser.add_argument("--script-editor-timeout-sec", type=int, default=180)
    parser.add_argument("--subtitle-mode", choices=["asr", "heuristic"], default="asr")
    parser.add_argument(
        "--subtitle-engine",
        choices=["stable_regroup", "legacy"],
        default="stable_regroup",
        help="subtitle alignment engine; stable_regroup uses whisper word timestamps + regroup",
    )
    parser.add_argument(
        "--subtitle-qa-policy",
        choices=["strict", "medium", "off"],
        default="strict",
    )
    parser.add_argument("--subtitle-max-chars", type=int, default=26)
    parser.add_argument("--subtitle-max-duration", type=float, default=3.2)
    parser.add_argument("--subtitle-font", default="本黑体")
    parser.add_argument("--subtitle-text-source", choices=["auto", "asr", "script"], default="script")
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--whisper-language", default="zh")
    parser.add_argument("--keys-env-file", default=str(DEFAULT_KEYS_ENV_FILE))
    parser.add_argument("--minimax-api-base", default="https://api.minimaxi.com")
    parser.add_argument("--minimax-key-env", default="MINIMAX_API_KEY")
    parser.add_argument("--minimax-model", default="speech-02-hd")
    parser.add_argument("--minimax-voice-id", help="direct MiniMax voice_id")
    parser.add_argument("--minimax-voice-name", help="MiniMax voice_name (e.g. 日常松弛男)")
    parser.add_argument("--siliconflow-api-base", default="https://api.siliconflow.cn")
    parser.add_argument("--siliconflow-key-env", default="SILICONFLW_API_KEY")
    parser.add_argument("--siliconflow-model", default="IndexTeam/IndexTTS-2")
    parser.add_argument("--siliconflow-voice-uri", help="direct SiliconFlow uploaded voice uri")
    parser.add_argument("--siliconflow-ref-audio", help="reference audio path for voice cloning")
    parser.add_argument("--siliconflow-ref-text", help="exact transcript for reference audio")
    parser.add_argument("--siliconflow-ref-name", default="日常松弛男", help="display name for uploaded reference voice")
    parser.add_argument("--siliconflow-asr-model", default="FunAudioLLM/SenseVoiceSmall")
    parser.add_argument(
        "--siliconflow-voice-cache",
        default=str(_CFG.voice_profile_path.parent / "siliconflow_voice_cache.json"),
    )
    parser.add_argument("--disable-siliconflow-voice-cache", action="store_true")
    parser.add_argument("--fallback-edge-on-minimax-fail", action="store_true")
    parser.add_argument("--fallback-edge-on-siliconflow-fail", action="store_true")
    parser.add_argument("--force-atempo-speed", action="store_true")
    parser.add_argument("--skip-audio", action="store_true", help="skip tts and audio injection")
    parser.add_argument("--keep-audio-effects", action="store_true", help="do not clear existing audio effects")
    parser.add_argument("--transition-primary", default="翻页")
    parser.add_argument("--transition-fallback", default="叠化")
    parser.add_argument("--transition-duration", default="0.35s")
    parser.add_argument("--smart-cut-mode", choices=["auto", "structured", "even"], default="auto")
    parser.add_argument("--json-report", default="")
    args = parser.parse_args()

    if not args.script_file and not args.article:
        raise ValueError("either --script-file or --article is required")

    raw_projects_root = (args.projects_root or "").strip()
    if re.match(r"^[A-Za-z]:\\", raw_projects_root):
        raise ValueError(
            "invalid --projects-root on macOS: received Windows-style path "
            f"'{raw_projects_root}'. Use an absolute mac path like "
            "'/Users/aki/Movies/JianyingPro/User Data/Projects/com.lveditor.draft'."
        )
    projects_root = Path(raw_projects_root).expanduser().resolve()
    workdir = Path(args.workdir).expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    article = Path(args.article).expanduser().resolve() if args.article else None
    script_file = Path(args.script_file).expanduser().resolve() if args.script_file else None
    transform_ts = Path(args.transform_ts).expanduser().resolve()
    script_to_srt = Path(args.script_to_srt).expanduser().resolve()
    scratch_builder = Path(args.scratch_builder).expanduser().resolve()

    if article and not article.exists():
        raise FileNotFoundError(f"article not found: {article}")
    if script_file and not script_file.exists():
        raise FileNotFoundError(f"script file not found: {script_file}")
    if not transform_ts.exists():
        raise FileNotFoundError(f"article transform not found: {transform_ts}")
    if not script_to_srt.exists():
        raise FileNotFoundError(f"script_to_srt not found: {script_to_srt}")
    if not scratch_builder.exists():
        raise FileNotFoundError(f"scratch builder not found: {scratch_builder}")

    assets = parse_assets(args)
    generated_script = prepare_script(
        article=article,
        script_file=script_file,
        transform_ts=transform_ts,
        new_name=args.new_name,
        workdir=workdir,
        duration_hint=args.duration,
    )
    generated_script = maybe_run_script_editor(
        script_path=generated_script,
        workdir=workdir,
        editor_cmd=args.script_editor_cmd,
        timeout_sec=args.script_editor_timeout_sec,
    )
    print(f"📝 Script: {generated_script}")
    warnings: List[str] = []
    voice_uri_used = ""
    subtitle_report: dict[str, Any] = {}

    if args.skip_audio:
        srt_out = workdir / f"{args.new_name}.srt"
        generate_srt_heuristic(script_to_srt, generated_script, srt_out, args.duration)
        raw_durations = parse_durations(args.durations)
        durations = raw_durations if len(raw_durations) == len(assets) else []
        if raw_durations and not durations:
            print("⚠️ durations count mismatch, fallback to even split")
            warnings.append("durations count mismatch, fallback to even split")
        transition_used = build_scratch_draft_from_srt(
            scratch_builder=scratch_builder,
            projects_root=projects_root,
            new_name=args.new_name,
            assets=assets,
            srt_path=srt_out,
            total_duration=args.duration,
            durations=durations,
            transition_primary=args.transition_primary,
            transition_fallback=args.transition_fallback,
            transition_duration=args.transition_duration,
            subtitle_font=args.subtitle_font,
        )
        tts_text = clean_script_text(
            generated_script,
            strict_verbatim=(args.script_format == "verbatim"),
        )
        duration_min = max(1e-9, args.duration / 60.0)
        char_count = count_speakable_chars(tts_text)
        cpm_report = {
            "char_count": char_count,
            "minutes": round(duration_min, 6),
            "cpm": round(char_count / duration_min, 3),
            "policy": "report_only",
        }
        speed_report = {
            "target_speed": float(args.voice_speed),
            "audio_duration_sec": float(args.duration),
            "char_count": char_count,
            "cpm": round(char_count / duration_min, 3),
        }
        draft_dir = projects_root / args.new_name
        report = {
            "draft_name": args.new_name,
            "draft_path": str(draft_dir),
            "script_path": str(generated_script),
            "audio_path": "",
            "srt_path": str(srt_out),
            "voice_uri_used": "",
            "audio_duration_sec": float(args.duration),
            "cpm_report": cpm_report,
            "speed_report": speed_report,
            "subtitle_report": subtitle_report,
            "warnings": warnings,
            "tts_provider": "none(skip_audio)",
            "subtitle_mode_used": "heuristic",
            "transition_used": transition_used,
        }
        maybe_write_report(args.json_report, report)
        print("✅ Draft generated without audio stage")
        print(f"📂 Draft: {projects_root / args.new_name}")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    load_env_file(Path(args.keys_env_file).expanduser().resolve())

    tts_text = clean_script_text(
        generated_script,
        strict_verbatim=(args.script_format == "verbatim"),
    )
    temp_audio_raw = workdir / f"{args.new_name}__tts_raw.m4a"
    temp_audio = workdir / f"{args.new_name}__tts_final.m4a"

    chosen_provider = args.tts_provider
    if chosen_provider == "auto":
        if os.getenv(args.siliconflow_key_env):
            chosen_provider = "siliconflow"
        elif os.getenv(args.minimax_key_env):
            chosen_provider = "minimax"
        else:
            chosen_provider = "edge"

    voice_label = ""
    if chosen_provider == "siliconflow":
        sf_key = os.getenv(args.siliconflow_key_env, "")
        if not sf_key:
            raise RuntimeError(
                f"SiliconFlow key not found in env var '{args.siliconflow_key_env}'. "
                f"Provide it in {args.keys_env_file} or switch --tts-provider edge."
            )
        try:
            voice_uri = (args.siliconflow_voice_uri or "").strip()
            cache_hit = False
            if not voice_uri:
                if not args.siliconflow_ref_audio:
                    raise RuntimeError(
                        "siliconflow requires --siliconflow-voice-uri or --siliconflow-ref-audio"
                    )
                ref_audio = Path(args.siliconflow_ref_audio).expanduser().resolve()
                if not ref_audio.exists():
                    raise FileNotFoundError(f"siliconflow reference audio missing: {ref_audio}")
                cache_path = Path(args.siliconflow_voice_cache).expanduser().resolve()
                cache_key = f"{args.siliconflow_model}:{sha1_file(ref_audio)}"
                cache_data = {} if args.disable_siliconflow_voice_cache else load_json(cache_path)
                voice_uri = str(cache_data.get(cache_key, "")).strip()
                if voice_uri:
                    cache_hit = True
                    print(f"▶ SiliconFlow voice cache hit: {voice_uri}")
                else:
                    ref_text = (args.siliconflow_ref_text or "").strip()
                    if not ref_text:
                        ref_text = siliconflow_transcribe_audio(
                            api_base=args.siliconflow_api_base,
                            api_key=sf_key,
                            audio_path=ref_audio,
                            asr_model=args.siliconflow_asr_model,
                        )
                        print(f"▶ SiliconFlow ASR text: {ref_text[:80]}...")
                    voice_uri = siliconflow_upload_voice(
                        api_base=args.siliconflow_api_base,
                        api_key=sf_key,
                        model=args.siliconflow_model,
                        ref_audio=ref_audio,
                        ref_text=ref_text,
                        custom_name=args.siliconflow_ref_name,
                    )
                    if not args.disable_siliconflow_voice_cache:
                        cache_data[cache_key] = voice_uri
                        save_json(cache_path, cache_data)
            print(f"▶ SiliconFlow TTS voice_uri={voice_uri} model={args.siliconflow_model}")
            voice_uri_used = voice_uri
            synthesize_audio_siliconflow(
                text=tts_text,
                api_base=args.siliconflow_api_base,
                api_key=sf_key,
                model=args.siliconflow_model,
                voice_uri=voice_uri,
                speed_ratio=(1.0 if args.force_atempo_speed else args.voice_speed),
                out_m4a=temp_audio_raw,
            )
            voice_label = f"SiliconFlow({'cached:' if cache_hit else ''}{voice_uri})"
        except Exception as e:
            if not args.fallback_edge_on_siliconflow_fail:
                raise
            print(f"⚠️ SiliconFlow synthesis failed ({e}), fallback to edge-tts")
            warnings.append(f"SiliconFlow synthesis failed: {e}")
            edge_voice = args.edge_voice or VOICE_STYLE_MAP[args.voice_style]
            synthesize_audio_edge(
                text=tts_text,
                voice=edge_voice,
                speed_ratio=args.voice_speed,
                out_m4a=temp_audio_raw,
            )
            chosen_provider = "edge"
            voice_label = f"edge-fallback({edge_voice})"
    elif chosen_provider == "minimax":
        mm_key = os.getenv(args.minimax_key_env, "")
        if not mm_key:
            raise RuntimeError(
                f"MiniMax key not found in env var '{args.minimax_key_env}'. "
                f"Provide it in {args.keys_env_file} or switch --tts-provider edge."
            )
        mm_voice_id = resolve_minimax_voice_id(
            api_base=args.minimax_api_base,
            api_key=mm_key,
            voice_style=args.voice_style,
            voice_id=args.minimax_voice_id,
            voice_name=args.minimax_voice_name,
        )
        try:
            print(f"▶ MiniMax TTS voice_id={mm_voice_id} model={args.minimax_model}")
            synthesize_audio_minimax(
                text=tts_text,
                api_base=args.minimax_api_base,
                api_key=mm_key,
                model=args.minimax_model,
                voice_id=mm_voice_id,
                speed_ratio=args.voice_speed,
                out_m4a=temp_audio_raw,
            )
            voice_label = f"MiniMax({mm_voice_id})"
        except Exception as e:
            if not args.fallback_edge_on_minimax_fail:
                raise
            print(f"⚠️ MiniMax synthesis failed ({e}), fallback to edge-tts")
            warnings.append(f"MiniMax synthesis failed: {e}")
            edge_voice = args.edge_voice or VOICE_STYLE_MAP[args.voice_style]
            synthesize_audio_edge(
                text=tts_text,
                voice=edge_voice,
                speed_ratio=args.voice_speed,
                out_m4a=temp_audio_raw,
            )
            chosen_provider = "edge"
            voice_label = f"edge-fallback({edge_voice})"
    else:
        edge_voice = args.edge_voice or VOICE_STYLE_MAP[args.voice_style]
        synthesize_audio_edge(
            text=tts_text,
            voice=edge_voice,
            speed_ratio=args.voice_speed,
            out_m4a=temp_audio_raw,
        )
        voice_label = f"Edge({edge_voice})"

    if args.force_atempo_speed:
        apply_atempo_speed(temp_audio_raw, temp_audio, args.voice_speed)
    else:
        shutil.copy2(temp_audio_raw, temp_audio)

    audio_duration_sec = probe_duration_us(temp_audio) / 1_000_000.0
    srt_out = workdir / f"{args.new_name}.srt"
    subtitle_label = "heuristic"
    used_stable_engine = False
    if args.subtitle_mode == "asr" and args.subtitle_engine == "stable_regroup":
        try:
            stable_out = generate_aligned_srt(
                audio_path=temp_audio,
                script_text=tts_text,
                output_srt=srt_out,
                whisper_model=args.whisper_model,
                whisper_language=args.whisper_language,
                qa_policy=args.subtitle_qa_policy,
                max_chars=args.subtitle_max_chars,
                max_duration=args.subtitle_max_duration,
            )
            subtitle_label = f"stable_regroup+whisper({args.whisper_model})"
            subtitle_report = dict(stable_out.get("report", {}))
            warnings.extend(stable_out.get("warnings", []))
            used_stable_engine = True
        except Exception as e:
            msg = f"stable subtitle engine failed, fallback to legacy: {e}"
            print(f"⚠️ {msg}")
            warnings.append(msg)

    if not used_stable_engine:
        if args.subtitle_mode == "asr":
            try:
                generate_srt_whisper(
                    audio_path=temp_audio,
                    output_srt=srt_out,
                    model=args.whisper_model,
                    language=args.whisper_language,
                )
                subtitle_label = f"whisper({args.whisper_model})"
            except Exception as e:
                print(f"⚠️ ASR subtitle failed ({e}), fallback to heuristic timeline")
                warnings.append(f"ASR subtitle failed, fallback to heuristic: {e}")
                generate_srt_heuristic(script_to_srt, generated_script, srt_out, audio_duration_sec)
        else:
            generate_srt_heuristic(script_to_srt, generated_script, srt_out, audio_duration_sec)

        if args.subtitle_engine == "legacy" and args.subtitle_text_source in ("script", "auto"):
            try:
                rewrite_srt_text_with_script(srt_out, tts_text)
                subtitle_label = f"{subtitle_label}+script_text"
            except Exception as e:
                msg = f"subtitle script-text rewrite failed: {e}"
                print(f"⚠️ {msg}")
                warnings.append(msg)

    raw_durations = parse_durations(args.durations)
    durations: List[float] = []
    if raw_durations and len(raw_durations) == len(assets):
        durations = scale_durations_to_total(raw_durations, audio_duration_sec)
    elif raw_durations:
        print("⚠️ durations count mismatch with assets, ignored and using even split")
        warnings.append("durations count mismatch with assets, ignored")
    else:
        if args.smart_cut_mode in ("auto", "structured"):
            smart = suggest_durations_from_script(tts_text, len(assets), audio_duration_sec)
            if smart:
                durations = smart
                print("▶ smart-cut applied from structured script blocks")
            elif args.smart_cut_mode == "structured":
                warnings.append("smart-cut structured mode failed; fallback even split")
        # even mode keeps durations empty -> scratch builder will even split by total duration.

    transition_used = build_scratch_draft_from_srt(
        scratch_builder=scratch_builder,
        projects_root=projects_root,
        new_name=args.new_name,
        assets=assets,
        srt_path=srt_out,
        total_duration=audio_duration_sec,
        durations=durations,
        transition_primary=args.transition_primary,
        transition_fallback=args.transition_fallback,
        transition_duration=args.transition_duration,
        subtitle_font=args.subtitle_font,
    )

    draft_dir = projects_root / args.new_name
    local_assets = draft_dir / "local_assets"
    local_assets.mkdir(parents=True, exist_ok=True)
    out_audio = local_assets / f"voice_{args.new_name}.m4a"
    shutil.copy2(temp_audio, out_audio)

    patch_draft_audio(
        projects_root=projects_root,
        draft_name=args.new_name,
        audio_path=out_audio,
        target_duration_sec=audio_duration_sec,
        clear_audio_effects=not args.keep_audio_effects,
    )

    duration_min = max(1e-9, audio_duration_sec / 60.0)
    char_count = count_speakable_chars(tts_text)
    cpm_report = {
        "char_count": char_count,
        "minutes": round(duration_min, 6),
        "cpm": round(char_count / duration_min, 3),
        "policy": "report_only",
    }
    speed_report = {
        "target_speed": float(args.voice_speed),
        "audio_duration_sec": round(audio_duration_sec, 6),
        "char_count": char_count,
        "cpm": round(char_count / duration_min, 3),
    }

    report = {
        "draft_name": args.new_name,
        "draft_path": str(draft_dir),
        "script_path": str(generated_script),
        "audio_path": str(out_audio),
        "srt_path": str(srt_out),
        "voice_uri_used": voice_uri_used,
        "audio_duration_sec": round(audio_duration_sec, 6),
        "cpm_report": cpm_report,
        "speed_report": speed_report,
        "subtitle_report": subtitle_report,
        "warnings": warnings,
        "tts_provider": chosen_provider,
        "subtitle_mode_used": subtitle_label,
        "transition_used": transition_used,
    }
    maybe_write_report(args.json_report, report)

    print("✅ Draft generated with audio")
    print(f"📂 Draft: {draft_dir}")
    print(f"🔊 Audio: {out_audio}")
    print(f"🎙️ Voice: {voice_label}, speed={args.voice_speed}")
    print(f"📝 Subtitle: {subtitle_label}")
    print(f"⏱️ Audio Duration: {audio_duration_sec:.3f}s")
    print(f"🧠 TTS Provider: {chosen_provider}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
