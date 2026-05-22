---
name: aki-personal-ip-cover
description: Generate Aki's personal IP profile reference images and topic cover images from local真人照片. Use this whenever the user asks for 个人IP图片、真人形象参考图、正脸/侧脸/全身图、个人头像封面、抖音封面、小红书封面、哔哩哔哩/B站封面、视频号封面, even if they only provide a topic title.
---

# Aki Personal IP Cover

## Overview

Create a consistent personal-brand visual workflow for Aki.

This skill does not build a real 3D model. It uses selected real photos to generate a realistic polished identity reference set, then uses that reference set to generate topic covers.

Default photo directory:

`/Users/aki/Documents/ObsidianVaults/Aki数字资产/00-Aki第二大脑/人设与风格/0.IP人设/000 真人相片`

Default cover style directory:

`/Users/aki/Documents/ObsidianVaults/Aki数字资产/02-IP个人话题/000 个人封面风格`

Style source files:

- Overall style prompt: `/Users/aki/Documents/ObsidianVaults/Aki数字资产/02-IP个人话题/000 个人封面风格/00.整体风格提示词.md`
- Skill symlink to the same prompt: `references/00.整体风格提示词.md`
- Visual style reference: `/Users/aki/Documents/ObsidianVaults/Aki数字资产/02-IP个人话题/000 个人封面风格/00.style-参考.png`
- Personal IP cutout reference: `references/00.IP人物抠图参考.png`

Single source of truth: do not duplicate the full style prompt in this skill. Always read the style text through `references/00.整体风格提示词.md`, which is a symlink to the Obsidian source file above.

Personal IP cutout source of truth: use `references/00.IP人物抠图参考.png`. The Obsidian style directory may keep a symlink to this file for compatibility, but the skill-owned reference lives in `references/`.

Non-negotiable style constraints from the linked prompt:

- Aki must keep the red jacket, Morgan forward fringe hairstyle, and consistent facial features.
- If `00.IP人物抠图参考.png` exists, use it as the primary person/identity reference before raw avatar photos.
- The person edge must be clearly outlined with a white cutout stroke.
- Do not use glow as a substitute for the person edge outline.
- Title text must stay large and eye-catching.
- Overall image style should stay close to Xiaohongshu cover style and work across platforms.
- Platform covers should stay visually unified, but not feel like repeated crops of one image. Vary composition, pose, background rhythm, and title block shape while keeping the same IP person and black-green tech brand language.
- Hands and props must look physically plausible. Do not let pens, laptops, cards, or other objects pass through fingers; avoid complex hand props when they risk malformed fingers.

Typography rule: keep semantic title phrases together. Do not split a phrase in a way that changes meaning, such as separating `AI提示词自由` from itself or making `一个网站搞定` read as `一个网站自由`.

Exact-title rule: when the user gives specific title text or line breaks, preserve them unless they explicitly ask for rewriting. Example: `第一性原理 / 使用 Claude Code 的 / 四个原则 / （Karpathy 启发指南）` must not be shortened to a different title.

Topic output rule: when making covers for a specific topic folder, copy every generated cover image back into that topic folder. Keep the original generated image in Codex's generated image directory.

Bilibili output rule: generate two separate Bilibili covers, one native `4:3` and one native `16:9`. The `16:9` cover should use the full horizontal canvas directly and must not reserve left/right disposable margins for a fake `4:3` crop.

## Workflow

1. Build a profile reference set:
   - Automatically scan the default photo directory.
   - Always prefer `00 头像.png` as the primary face reference when it exists; fallback to `0 头像.JPG`, then `头像.JPG`.
   - Select 3-5 complementary photos by resolution and orientation.
   - Convert HEIC files to temporary JPEG references for Codex `image_gen`.
   - Generate prompts for:
     - front face
     - left side face
     - right side face
     - half body
     - full body
     - gesture
2. Generate topic covers:
   - Read the profile reference set.
   - Read the default cover style directory before writing cover prompts.
   - Use `00.style-参考.png` as the visual style reference and `00.整体风格提示词.md` as the style rule source.
   - If `00.IP人物抠图参考.png` exists, use it as the primary identity reference. It should override raw headshots for cover generation.
   - Every generated prompt must explicitly include the full source path for the overall style prompt and visual style reference.
   - If the topic folder has a `案例/` directory, use those images as the case-panel/background reference.
   - Use generated reference images first when available; otherwise use the selected source photos.
   - Generate five cover outputs:
     - douyin: 9:16
     - xhs: 3:4
     - bilibili_4x3: 4:3, native Bilibili cover
     - bilibili_16x9: 16:9, native horizontal Bilibili cover, no 4:3 crop safety margins
     - wechat_channels: 9:16, with face/title kept in a 3:4-safe center crop and empty top/bottom safety margins
   - Safe areas:
     - 9:16 vertical covers: keep key content in the centered 3:4 crop area; leave the top/bottom 12.5% as safety margins.
     - Bilibili 4:3 covers: compose directly for the full 4:3 canvas.
     - Bilibili 16:9 covers: compose directly for the full 16:9 canvas; do not design it as a crop-safe 4:3 image.

## Commands

Build profile prompts only:

```bash
python3 /Users/aki/Development/code/aki-skills/skills/aki-personal-ip-cover/scripts/generate_personal_ip.py \
  build_profile \
  --out /absolute/path/to/output
```

Generate topic cover prompts only:

```bash
python3 /Users/aki/Development/code/aki-skills/skills/aki-personal-ip-cover/scripts/generate_personal_ip.py \
  cover \
  --title "你的话题标题" \
  --profile /absolute/path/to/output/profile \
  --out /absolute/path/to/output/covers \
  --topic-dir /absolute/path/to/topic \
  --style-dir "/Users/aki/Documents/ObsidianVaults/Aki数字资产/02-IP个人话题/000 个人封面风格"
```

## Options

- `--photo-dir`: source photo directory. Defaults to Aki's local真人相片 directory.
- `--out`: output directory.
- `--title`: topic title for cover generation.
- `--profile`: profile directory created by `build_profile`.
- `--style-dir`: personal cover style reference directory. Defaults to `000 个人封面风格`.
- `--topic-dir`: current topic directory. When provided, case references default to `TOPIC_DIR/案例`.
- `--case-dir`: case image reference directory. Overrides `TOPIC_DIR/案例`.
- `--max-photos`: number of source photos to auto-select, default 5.

## Outputs

Profile:

- `profile/selected_photos.json`
- `profile/prompts/*.md`
- `profile/images/front.png` after Codex `image_gen` rendering
- `profile/images/left-side.png` after Codex `image_gen` rendering
- `profile/images/right-side.png` after Codex `image_gen` rendering
- `profile/images/half-body.png` after Codex `image_gen` rendering
- `profile/images/full-body.png` after Codex `image_gen` rendering
- `profile/images/gesture.png` after Codex `image_gen` rendering
- `profile/profile-card.md`
- `metadata.json`

Covers:

- `covers/prompts/*.md`
- `covers/douyin/*.png` after Codex `image_gen` rendering
- `covers/xhs/*.png` after Codex `image_gen` rendering
- `covers/bilibili_4x3/*.png` after Codex `image_gen` rendering
- `covers/bilibili_16x9/*.png` after Codex `image_gen` rendering
- `covers/wechat_channels/*.png` after Codex `image_gen` rendering
- `covers/metadata.json`
- `covers/metadata.json` includes `style_dir` and `style_reference_images`.
- `covers/metadata.json` includes `topic_dir`, `case_dir`, and `case_reference_images`.

## Codex Image Gen Workflow

When using Codex built-in `image_gen`:

1. Read the topic content file and the topic folder.
2. Use `references/00.IP人物抠图参考.png` as the primary identity reference when it exists; otherwise use `00 头像.png`.
3. Read `000 个人封面风格/00.style-参考.png` and `00.整体风格提示词.md`.
4. Put the style source paths into the image prompt: `整体风格提示词来源：...` and `封面风格参考图来源：...`.
5. Read topic case images from `话题目录/案例/` when present.
6. Treat `00.style-参考.png` only as a style reference. Do not use it as a base image, do not edit it, and do not layer text on top of it.
7. Generate a new cover from the identity reference, topic title, and personal IP constraints. Aki must be cut out as a new foreground person with a white outline.
8. Generate one requested platform image at a time.
   - For Bilibili 4:3, prompt must explicitly say: `native 4:3 Bilibili cover, use the full 4:3 canvas directly`.
   - For Bilibili 16:9, prompt must explicitly say: `native 16:9 Bilibili cover, use the full 16:9 canvas directly, do not reserve 4:3 crop safety margins`.
9. Immediately copy the latest generated image back to the topic folder using a platform-specific filename:
   - `封面-9x16-标题关键词.png`
   - `封面-3x4-标题关键词.png`
   - `封面-bilibili-4x3-标题关键词.png`
   - `封面-bilibili-16x9-标题关键词.png`
   - `封面-视频号-标题关键词.png`
10. Do not delete the original generated image.

## Personal IP Cutout Reference

Create or refresh this file when Aki's cover identity drifts:

`/Users/aki/Development/code/aki-skills/skills/aki-personal-ip-cover/references/00.IP人物抠图参考.png`

How to make it with Codex `image_gen`:

- Use the best recent generated cover or `00.style-参考.png` only to recover the IP body, red jacket, white cutout edge, and cover-ready pose.
- Use `00 头像.png` to correct the face identity, skin tone, facial features, glasses, and Morgan forward fringe hairstyle.
- Output only Aki as a clean foreground cutout on transparent background when possible; otherwise use pure white or a flat solid color background.
- No title text, no logo, no QR code, no background scene, no UI panels, no old cover elements.
- Keep the red jacket, hair, face color, glasses, and white cutout stroke consistent with the accepted cover style.
- Save the generated image as `references/00.IP人物抠图参考.png` in this skill directory and keep the original generated image in Codex's generated image directory.
- It is acceptable for the default cover style directory to contain a symlink named `00.IP人物抠图参考.png` pointing back to the skill reference.

## Platform Ratios

- Douyin: `9:16`. Keep key content in the centered `3:4` crop area; leave the top/bottom 12.5% free of critical text, face, logo, and key objects.
- Xiaohongshu: `3:4`
- Bilibili 4:3: generate a separate native `4:3` image.
- Bilibili 16:9: generate a separate native `16:9` image; use the full canvas and do not leave fake 4:3 crop safety margins.
- WeChat Channels: `9:16`. Keep key content in the centered `3:4` crop area; leave the top/bottom 12.5% free of critical text, face, logo, and key objects.

## Notes

- Do not copy Aki's source photos into the repository.
- The generated IP cutout reference is allowed to live in this skill's `references/` directory because it is the reusable personal IP asset, not a raw source photo.
- Do not hardcode API keys. Credentials must come from `/Users/aki/.config/ai/keys.env` or existing provider config.
- Inside Codex, render only with built-in `image_gen`.
- Do not use Comfly, provider fallbacks, or any external paid image API in this skill.
