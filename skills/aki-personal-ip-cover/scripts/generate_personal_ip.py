#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]


DEFAULT_PHOTO_DIR = Path(
    "/Users/aki/Documents/ObsidianVaults/Aki数字资产/00-Aki第二大脑/人设与风格/0.IP人设/000 真人相片"
)
DEFAULT_COVER_STYLE_DIR = Path(
    "/Users/aki/Documents/ObsidianVaults/Aki数字资产/02-IP个人话题/000 个人封面风格"
)
DEFAULT_STYLE_PROMPT_LINK = SKILL_ROOT / "references" / "00.整体风格提示词.md"
DEFAULT_IP_CUTOUT_REFERENCE = SKILL_ROOT / "references" / "00.IP人物抠图参考.png"
PRIMARY_FACE_NAMES = ("00 头像.png", "0 头像.JPG", "头像.JPG")
IP_CUTOUT_REFERENCE_NAMES = (
    "00.IP人物抠图参考.png",
    "00.IP人物抠图参考-透明底.png",
    "00.IP人物抠图参考-白底.png",
)
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
    (
        "douyin",
        "9:16",
        "抖音封面",
        "vertical short-video cover, keep face and title inside the centered 3:4 safe crop, leave the top and bottom 12.5% free of critical text or face details",
    ),
    ("xhs", "3:4", "小红书封面", "vertical social cover, strong title hierarchy, readable in feed"),
    (
        "bilibili_4x3",
        "4:3",
        "哔哩哔哩视频封面 4:3",
        "Bilibili direct 4:3 cover, no hidden crop simulation; keep title, face, body, gesture, and key chips inside the canvas with clean platform-safe margins",
    ),
    (
        "bilibili_16x9",
        "16:9",
        "哔哩哔哩视频封面 16:9",
        "Bilibili native 16:9 cover, use the full 16:9 canvas directly; do not reserve left/right disposable margins for a 4:3 crop; compose as a complete horizontal poster",
    ),
    (
        "wechat_channels",
        "9:16",
        "视频号封面",
        "vertical WeChat Channels cover, keep face and title inside the centered 3:4 safe crop, leave the top and bottom 12.5% free of critical text or face details",
    ),
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


@dataclass(frozen=True)
class CoverStyle:
    prompt: str
    prompt_path: Path | None
    images: list[Path]


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
            try:
                width = int(line.split(":", 1)[1].strip())
            except ValueError:
                width = 0
        elif line.startswith("pixelHeight:"):
            try:
                height = int(line.split(":", 1)[1].strip())
            except ValueError:
                height = 0
    return width, height


def photo_score(path: Path, width: int, height: int) -> tuple[float, str]:
    name = path.name
    suffix = path.suffix.lower()
    pixels = width * height
    score = min(pixels / 12_000_000, 1.0) * 60
    reasons: list[str] = [f"{width}x{height}"]
    if name in PRIMARY_FACE_NAMES:
        score += 120 - PRIMARY_FACE_NAMES.index(name) * 10
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
    primary = [p for p in photos if p.path.name in PRIMARY_FACE_NAMES]
    primary.sort(key=lambda p: PRIMARY_FACE_NAMES.index(p.path.name))
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


def load_cover_style(style_dir: Path) -> CoverStyle:
    if not style_dir.exists():
        return CoverStyle(prompt="", prompt_path=None, images=[])
    prompt_path = DEFAULT_STYLE_PROMPT_LINK if DEFAULT_STYLE_PROMPT_LINK.exists() else style_dir / "00.整体风格提示词.md"
    style_prompt = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""
    style_images = [
        path
        for path in sorted(style_dir.iterdir(), key=lambda p: p.name)
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_SUFFIXES
        and path.name not in IP_CUTOUT_REFERENCE_NAMES
    ]
    return CoverStyle(
        prompt=style_prompt,
        prompt_path=prompt_path if prompt_path.exists() else None,
        images=[path.resolve() for path in style_images],
    )


def load_ip_cutout_reference_images(style_dir: Path) -> list[Path]:
    refs: list[Path] = []
    if DEFAULT_IP_CUTOUT_REFERENCE.is_file():
        refs.append(DEFAULT_IP_CUTOUT_REFERENCE.resolve())
    if style_dir.exists():
        for name in IP_CUTOUT_REFERENCE_NAMES:
            path = style_dir / name
            if path.is_file() and path.resolve() not in refs:
                refs.append(path.resolve())
    return refs


def load_case_images(case_dir: Path | None) -> list[Path]:
    if case_dir is None or not case_dir.exists():
        return []
    return [
        path
        for path in sorted(case_dir.iterdir(), key=lambda p: p.name)
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    ]


def image_reference_block(label: str, paths: list[Path]) -> str:
    if not paths:
        return ""
    lines = []
    for path in paths[:8]:
        width, height = run_sips_dims(path)
        dims = f"{width}x{height}" if width and height else "unknown size"
        lines.append(f"- {path}: {dims}")
    return f"""
{label}：
{chr(10).join(lines)}

"""


def cover_prompt(
    title: str,
    platform_label: str,
    aspect_ratio: str,
    platform_instruction: str,
    style_prompt: str = "",
    style_prompt_path: Path | None = None,
    identity_images: list[Path] | None = None,
    style_images: list[Path] | None = None,
    case_images: list[Path] | None = None,
) -> str:
    style_block = ""
    if style_prompt:
        source_line = f"整体风格提示词来源：{style_prompt_path}\n" if style_prompt_path else ""
        image_source_lines = ""
        if style_images:
            image_source_lines = "\n".join(f"封面风格参考图来源：{path}" for path in style_images[:8]) + "\n"
        style_block = f"""
固定个人封面风格：
{source_line}{image_source_lines}
{style_prompt}

"""
    reference_blocks = image_reference_block("个人IP人物抠图参考图（优先身份参考）", identity_images or [])
    reference_blocks += image_reference_block("个人封面风格参考图", style_images or [])
    reference_blocks += image_reference_block("话题案例图参考", case_images or [])
    return f"""你是个人 IP 内容封面设计师。请基于随请求提供的个人形象参考图，为下面的话题生成一张{platform_label}。

标题：
{title}

{style_block}
{reference_blocks}
平台与比例：
- 平台：{platform_label}
- 画幅比例：{aspect_ratio}
- 设计重点：{platform_instruction}

设计要求：
- 如果存在“个人IP人物抠图参考图”，优先参考这张图生成 Aki；它定义人物发型、脸部肤色、五官、红色外套、半身抠图质感和白色描边。
- 人物必须保持与参考图一致：五官、脸型、眼睛、鼻子、嘴型、牙齿、笑容、圆角金属框眼镜、摩根前刺发型、红色外套都要一致。
- 不要把封面风格参考图当成底图直接改字或叠加；它只用于学习黑绿高对比、粗体大字、笔刷和科技网格的风格。
- 同一组选题的多平台封面必须统一但不能像同一张图裁切：保留同一 IP 人物和黑绿科技品牌语言，但变化构图、动作、背景节奏和标题块形状。
- 人物动作必须自然。避免复杂道具穿过手指；如果使用笔记本电脑、平板或卡片，手指必须完整、清楚、没有穿模、融合、多指或少指。
- 标题是画面核心信息，中文必须清晰可读，字号要大；不要堆很多小字，小字可以省略。
- 标题短语不能被错误拆分；核心短语必须作为完整视觉单元排版，避免让读者误读成另一句话。
- 标题不能遮挡人脸，人物脸部必须完整可见。
- 风格优先参考固定个人封面风格：黑绿高对比、小红书封面感、粗体大字、白色人物描边、醒目但不杂乱。
- 如果有话题案例图，背景和案例面板优先参考这些案例图；可以放 2-3 张倾斜案例画面，但不要用小字堆满画面。
- 不要出现无关 logo、水印、二维码、平台 UI、错误英文、乱码。
"""


def planned_image_gen_output(output_path: Path, aspect_ratio: str) -> dict[str, Any]:
    return {
        "output": str(output_path),
        "rendered": False,
        "renderer": "codex_builtin_image_gen",
        "aspect_ratio": aspect_ratio,
        "note": "Use Codex built-in image_gen with the generated prompt and listed reference image paths.",
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
            "primary_face_reference": photo.path.name in PRIMARY_FACE_NAMES,
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
        render_records.append(planned_image_gen_output(output_path, "3:4"))
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
            "reference_images": [str(path) for path in refs],
            "prompts": prompt_index,
            "planned_outputs": render_records,
        },
    )
    print(f"Profile written to: {profile_dir}")
    print("Prompt-only mode. Render with Codex built-in image_gen.")


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
    style_dir = Path(args.style_dir).expanduser().resolve()
    cover_style = load_cover_style(style_dir)
    ip_cutout_refs = load_ip_cutout_reference_images(style_dir)
    if ip_cutout_refs:
        refs = ip_cutout_refs
    topic_dir = Path(args.topic_dir).expanduser().resolve() if args.topic_dir else None
    case_dir = Path(args.case_dir).expanduser().resolve() if args.case_dir else (topic_dir / "案例" if topic_dir else None)
    case_images = load_case_images(case_dir)
    records: list[dict[str, Any]] = []
    for platform, ratio, label, instruction in COVER_TARGETS:
        prompt = cover_prompt(
            args.title,
            label,
            ratio,
            instruction,
            cover_style.prompt,
            cover_style.prompt_path,
            refs,
            cover_style.images,
            case_images,
        )
        prompt_path = prompts_dir / f"{platform}.md"
        output_path = out / platform / "cover.png"
        write_text(prompt_path, prompt)
        record = planned_image_gen_output(output_path, ratio)
        record.update({"platform": platform, "label": label, "prompt": str(prompt_path)})
        records.append(record)
    write_json(
        out / "metadata.json",
        {
            "mode": "cover",
            "title": args.title,
            "profile_dir": str(profile_dir),
            "reference_images": [str(path) for path in refs],
            "ip_cutout_reference_images": [str(path) for path in ip_cutout_refs],
            "style_dir": str(style_dir),
            "style_prompt_path": str(cover_style.prompt_path) if cover_style.prompt_path else "",
            "style_reference_images": [str(path) for path in cover_style.images],
            "topic_dir": str(topic_dir) if topic_dir else "",
            "case_dir": str(case_dir) if case_dir else "",
            "case_reference_images": [str(path) for path in case_images],
            "covers": records,
        },
    )
    print(f"Covers written to: {out}")
    print("Prompt-only mode. Render with Codex built-in image_gen.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Aki personal IP profile references and covers.")
    sub = parser.add_subparsers(dest="command", required=True)

    profile = sub.add_parser("build_profile", help="Auto-select photos and build profile reference images.")
    profile.add_argument("--photo-dir", default=str(DEFAULT_PHOTO_DIR), help="Source photo directory.")
    profile.add_argument("--out", required=True, help="Output root directory.")
    profile.add_argument("--max-photos", type=int, default=5, help="Maximum selected source photos.")
    profile.set_defaults(func=build_profile)

    cover = sub.add_parser("cover", help="Generate topic covers from a built profile.")
    cover.add_argument("--title", required=True, help="Topic title.")
    cover.add_argument("--profile", required=True, help="Profile directory from build_profile.")
    cover.add_argument("--out", required=True, help="Cover output directory.")
    cover.add_argument("--style-dir", default=str(DEFAULT_COVER_STYLE_DIR), help="Personal cover style reference directory.")
    cover.add_argument("--topic-dir", default="", help="Topic directory. Defaults case references to TOPIC_DIR/案例 when provided.")
    cover.add_argument("--case-dir", default="", help="Topic case image reference directory. Overrides TOPIC_DIR/案例.")
    cover.set_defaults(func=generate_covers)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
