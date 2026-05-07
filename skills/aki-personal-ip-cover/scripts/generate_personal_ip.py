#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_DIR = REPO_ROOT / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from image_provider import (  # noqa: E402
    ImageProviderError,
    load_provider_configs,
    render_image_with_provider,
)


DEFAULT_PHOTO_DIR = Path(
    "/Users/aki/Documents/ObsidianVaults/Aki数字资产/00-Aki第二大脑/人设与风格/0.IP人设/真人相片"
)
PRIMARY_FACE_NAME = "头像.JPG"
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
PROFILE_VIEWS = [
    ("front", "正脸头像", "front-facing headshot, looking at camera"),
    ("left-side", "左侧脸", "left side profile, 70-90 degree angle"),
    ("right-side", "右侧脸", "right side profile, 70-90 degree angle"),
    ("half-body", "半身形象", "half-body portrait, natural personal-brand pose"),
    ("full-body", "全身形象", "full-body standing portrait, clean outfit silhouette"),
    ("gesture", "常用姿势", "upper-body speaking gesture, confident and friendly"),
]
COVER_TARGETS = [
    ("xhs", "4:5", "小红书封面", "vertical social cover, strong title hierarchy"),
    ("wechat", "2.35:1", "公众号首图", "wide WeChat article cover, readable at small size"),
    ("video", "9:16", "视频号/抖音封面", "vertical short-video cover, face-safe title layout"),
]


@dataclass(frozen=True)
class PhotoInfo:
    path: Path
    width: int
    height: int
    score: float
    reason: str

    @property
    def orientation(self) -> str:
        if self.width > self.height * 1.12:
            return "landscape"
        if self.height > self.width * 1.12:
            return "portrait"
        return "square"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_sips_dims(path: Path) -> tuple[int, int]:
    proc = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return 0, 0
    width = 0
    height = 0
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("pixelWidth:"):
            width = int(line.split(":", 1)[1].strip())
        elif line.startswith("pixelHeight:"):
            height = int(line.split(":", 1)[1].strip())
    return width, height


def photo_score(path: Path, width: int, height: int) -> tuple[float, str]:
    name = path.name
    suffix = path.suffix.lower()
    pixels = width * height
    score = min(pixels / 12_000_000, 1.0) * 60
    reasons: list[str] = [f"{width}x{height}"]
    if name == PRIMARY_FACE_NAME:
        score += 100
        reasons.append("主头像")
    if height > width:
        score += 12
        reasons.append("竖图适合人像")
    elif width == height:
        score += 8
        reasons.append("方图适合头像")
    else:
        score += 4
        reasons.append("横图补充场景/姿态")
    if suffix in {".jpg", ".jpeg", ".png"}:
        score += 8
        reasons.append("接口友好格式")
    elif suffix == ".heic":
        score += 2
        reasons.append("HEIC需转换")
    if width < 800 or height < 800:
        score -= 30
        reasons.append("分辨率偏低")
    return score, "；".join(reasons)


def scan_photos(photo_dir: Path) -> list[PhotoInfo]:
    if not photo_dir.exists():
        raise FileNotFoundError(f"Photo directory not found: {photo_dir}")
    photos: list[PhotoInfo] = []
    for path in sorted(photo_dir.iterdir(), key=lambda p: p.name):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        width, height = run_sips_dims(path)
        if not width or not height:
            continue
        score, reason = photo_score(path, width, height)
        photos.append(PhotoInfo(path=path, width=width, height=height, score=score, reason=reason))
    return photos


def select_photos(photo_dir: Path, max_photos: int) -> list[PhotoInfo]:
    photos = scan_photos(photo_dir)
    if not photos:
        raise RuntimeError(f"No usable photos found in {photo_dir}")
    max_photos = max(1, min(max_photos, 8))
    primary = [p for p in photos if p.path.name == PRIMARY_FACE_NAME]
    selected: list[PhotoInfo] = primary[:1]
    selected_paths = {p.path for p in selected}
    buckets = {
        "portrait": [p for p in photos if p.orientation == "portrait" and p.path not in selected_paths],
        "landscape": [p for p in photos if p.orientation == "landscape" and p.path not in selected_paths],
        "square": [p for p in photos if p.orientation == "square" and p.path not in selected_paths],
    }
    for bucket in buckets.values():
        bucket.sort(key=lambda p: p.score, reverse=True)
    for orientation in ("portrait", "square", "landscape"):
        if len(selected) >= max_photos:
            break
        if buckets[orientation]:
            item = buckets[orientation].pop(0)
            selected.append(item)
            selected_paths.add(item.path)
    remaining = [p for p in photos if p.path not in selected_paths]
    remaining.sort(key=lambda p: p.score, reverse=True)
    for item in remaining:
        if len(selected) >= max_photos:
            break
        selected.append(item)
    return selected


def convert_to_jpeg(src: Path, dst: Path) -> Path:
    ensure_dir(dst.parent)
    suffix = src.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        shutil.copy2(src, dst)
        return dst
    proc = subprocess.run(
        ["sips", "-s", "format", "jpeg", str(src), "--out", str(dst)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not dst.exists():
        raise RuntimeError(f"Failed to convert reference image: {src}\n{proc.stderr.strip()}")
    return dst


def prepared_reference_images(photos: list[PhotoInfo], cache_dir: Path) -> list[Path]:
    refs: list[Path] = []
    ensure_dir(cache_dir)
    for idx, photo in enumerate(photos, start=1):
        dst = cache_dir / f"ref-{idx:02d}.jpg"
        refs.append(convert_to_jpeg(photo.path, dst))
    return refs


def encode_reference_images(paths: list[Path]) -> list[str]:
    values: list[str] = []
    for path in paths:
        values.append(base64.b64encode(path.read_bytes()).decode("ascii"))
    return values


def profile_prompt(label: str, view_instruction: str, selected: list[PhotoInfo]) -> str:
    selected_lines = "\n".join(
        f"- {idx}. {photo.path.name}: {photo.width}x{photo.height}, {photo.reason}"
        for idx, photo in enumerate(selected, start=1)
    )
    return f"""你是个人品牌视觉设计师。请基于随请求提供的真人参考图，还原同一个人的真实精修形象。

目标画面：{label}
视角/姿态：{view_instruction}

人物一致性要求：
- 保留参考图中的核心身份特征：年轻亚洲男性、短黑发、圆角金属框眼镜、亲和笑容、干净真实的脸部比例。
- 生成结果要像同一个真实的人，而不是泛化的男模或卡通角色。
- 风格是真实但精修：商业摄影质感、自然皮肤、干净光线、可信的人像细节。
- 不要生成夸张 3D 卡通、赛博风、过度磨皮、塑料皮肤、AI 感强的脸。
- 背景简洁，不要文字、logo、水印、二维码。
- 输出适合作为后续个人 IP 封面参考图。

自动选用的参考照片：
{selected_lines}
"""


def cover_prompt(title: str, platform_label: str, aspect_ratio: str, platform_instruction: str) -> str:
    return f"""你是个人 IP 内容封面设计师。请基于随请求提供的个人形象参考图，为下面的话题生成一张{platform_label}。

标题：
{title}

平台与比例：
- 平台：{platform_label}
- 画幅比例：{aspect_ratio}
- 设计重点：{platform_instruction}

设计要求：
- 人物必须保持与参考图一致：年轻亚洲男性、短黑发、圆角金属框眼镜、真实亲和、有个人品牌辨识度。
- 标题是画面核心信息，中文必须清晰可读，允许自然换行。
- 标题不能遮挡人脸，人物脸部必须完整可见。
- 风格是真实但精修，像高质量内容封面，不要卡通化，不要真 3D 模型感。
- 背景可以结合 AI、科技、内容创作、个人观察等抽象元素，但不要抢标题和人物。
- 不要出现无关 logo、水印、二维码、平台 UI、错误英文、乱码。
"""


def load_comfly_reference_config(aspect_ratio: str, refs: list[Path]) -> tuple[str, dict[str, Any]]:
    configs = load_provider_configs()
    if "comfly" not in configs:
        raise ImageProviderError(
            provider="comfly",
            category="config",
            message="Reference-image generation requires Comfly config. Set COMFLY_API_KEY and COMFLY_IMAGE_MODEL.",
            recoverable=False,
        )
    config = dict(configs["comfly"])
    config["aspect_ratio"] = aspect_ratio
    config["image_size"] = config.get("image_size") or "2K"
    config["image"] = encode_reference_images(refs)
    return "comfly", config


def render_one(
    prompt: str,
    output_path: Path,
    aspect_ratio: str,
    refs: list[Path],
    confirm: bool,
    image_provider: str,
) -> dict[str, Any]:
    if image_provider != "comfly":
        raise ValueError("Reference-image generation currently supports only --image-provider comfly.")
    if not confirm:
        return {"output": str(output_path), "rendered": False, "provider": image_provider, "aspect_ratio": aspect_ratio}
    provider, config = load_comfly_reference_config(aspect_ratio, refs)
    result = render_image_with_provider(prompt, output_path, provider, config)
    return {
        "output": str(result.output_path),
        "rendered": True,
        "provider": result.provider_used,
        "image_format": result.image_format,
        "aspect_ratio": aspect_ratio,
    }


def build_profile(args: argparse.Namespace) -> None:
    out = Path(args.out).expanduser().resolve()
    profile_dir = out / "profile"
    prompts_dir = profile_dir / "prompts"
    images_dir = profile_dir / "images"
    refs_dir = profile_dir / ".refs"
    selected = select_photos(Path(args.photo_dir).expanduser(), args.max_photos)
    refs = prepared_reference_images(selected, refs_dir)

    selected_payload = [
        {
            "path": str(photo.path),
            "width": photo.width,
            "height": photo.height,
            "orientation": photo.orientation,
            "score": round(photo.score, 3),
            "reason": photo.reason,
            "primary_face_reference": photo.path.name == PRIMARY_FACE_NAME,
        }
        for photo in selected
    ]
    write_json(profile_dir / "selected_photos.json", selected_payload)

    render_records: list[dict[str, Any]] = []
    prompt_index: list[dict[str, str]] = []
    for slug, label, instruction in PROFILE_VIEWS:
        prompt = profile_prompt(label, instruction, selected)
        prompt_path = prompts_dir / f"{slug}.md"
        output_path = images_dir / f"{slug}.png"
        write_text(prompt_path, prompt)
        render_records.append(render_one(prompt, output_path, "3:4", refs, args.confirm, args.image_provider))
        prompt_index.append({"slug": slug, "label": label, "prompt": str(prompt_path), "output": str(output_path)})

    profile_card = [
        "# Aki Personal IP Profile",
        "",
        "## Selected source photos",
        *[f"- {Path(item['path']).name}: {item['reason']}" for item in selected_payload],
        "",
        "## Generated views",
        *[f"- {item['label']}: `{Path(item['output']).name}`" for item in prompt_index],
        "",
        "## Style",
        "真实但精修，保留本人特征，适合作为个人品牌封面形象参考。",
        "",
    ]
    write_text(profile_dir / "profile-card.md", "\n".join(profile_card))
    write_json(
        out / "metadata.json",
        {
            "mode": "build_profile",
            "profile_dir": str(profile_dir),
            "photo_dir": str(Path(args.photo_dir).expanduser()),
            "selected_photos": selected_payload,
            "prompts": prompt_index,
            "renders": render_records,
            "image_provider": args.image_provider,
        },
    )
    print(f"Profile written to: {profile_dir}")
    if not args.confirm:
        print("Prompt-only mode. Re-run with --confirm to render images.")


def profile_reference_paths(profile_dir: Path) -> list[Path]:
    image_dir = profile_dir / "images"
    generated = [
        image_dir / "front.png",
        image_dir / "half-body.png",
        image_dir / "full-body.png",
        image_dir / "left-side.png",
        image_dir / "right-side.png",
    ]
    existing = [path for path in generated if path.exists()]
    if existing:
        return existing[:5]
    selected_path = profile_dir / "selected_photos.json"
    if not selected_path.exists():
        raise FileNotFoundError(f"Missing profile references: {selected_path}")
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    photos = [PhotoInfo(Path(item["path"]), int(item["width"]), int(item["height"]), 0, item.get("reason", "")) for item in selected]
    return prepared_reference_images(photos[:5], profile_dir / ".cover-refs")


def generate_covers(args: argparse.Namespace) -> None:
    out = Path(args.out).expanduser().resolve()
    profile_dir = Path(args.profile).expanduser().resolve()
    prompts_dir = out / "prompts"
    refs = profile_reference_paths(profile_dir)
    records: list[dict[str, Any]] = []
    for platform, ratio, label, instruction in COVER_TARGETS:
        prompt = cover_prompt(args.title, label, ratio, instruction)
        prompt_path = prompts_dir / f"{platform}.md"
        output_path = out / platform / "cover.png"
        write_text(prompt_path, prompt)
        record = render_one(prompt, output_path, ratio, refs, args.confirm, args.image_provider)
        record.update({"platform": platform, "label": label, "prompt": str(prompt_path)})
        records.append(record)
    write_json(
        out / "metadata.json",
        {
            "mode": "cover",
            "title": args.title,
            "profile_dir": str(profile_dir),
            "reference_images": [str(path) for path in refs],
            "covers": records,
            "image_provider": args.image_provider,
        },
    )
    print(f"Covers written to: {out}")
    if not args.confirm:
        print("Prompt-only mode. Re-run with --confirm to render images.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Aki personal IP profile references and covers.")
    sub = parser.add_subparsers(dest="command", required=True)

    profile = sub.add_parser("build_profile", help="Auto-select photos and build profile reference images.")
    profile.add_argument("--photo-dir", default=str(DEFAULT_PHOTO_DIR), help="Source photo directory.")
    profile.add_argument("--out", required=True, help="Output root directory.")
    profile.add_argument("--max-photos", type=int, default=5, help="Maximum selected source photos.")
    profile.add_argument("--image-provider", choices=["comfly"], default="comfly", help="Image provider.")
    profile.add_argument("--confirm", action="store_true", help="Render images. Omit for prompt-only mode.")
    profile.set_defaults(func=build_profile)

    cover = sub.add_parser("cover", help="Generate topic covers from a built profile.")
    cover.add_argument("--title", required=True, help="Topic title.")
    cover.add_argument("--profile", required=True, help="Profile directory from build_profile.")
    cover.add_argument("--out", required=True, help="Cover output directory.")
    cover.add_argument("--image-provider", choices=["comfly"], default="comfly", help="Image provider.")
    cover.add_argument("--confirm", action="store_true", help="Render images. Omit for prompt-only mode.")
    cover.set_defaults(func=generate_covers)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except ImageProviderError as exc:
        raise SystemExit(f"{exc.provider} {exc.category}: {exc}") from exc


if __name__ == "__main__":
    main()
