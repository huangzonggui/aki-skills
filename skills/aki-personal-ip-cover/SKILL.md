---
name: aki-personal-ip-cover
description: Generate Aki's personal IP profile reference images and topic cover images from local真人照片. Use this whenever the user asks for 个人IP图片、真人形象参考图、正脸/侧脸/全身图、个人头像封面、小红书封面、公众号首图、视频号/抖音封面, even if they only provide a topic title.
---

# Aki Personal IP Cover

## Overview

Create a consistent personal-brand visual workflow for Aki.

This skill does not build a real 3D model. It uses selected real photos to generate a realistic polished identity reference set, then uses that reference set to generate topic covers.

Default photo directory:

`/Users/aki/Documents/ObsidianVaults/Aki数字资产/00-Aki第二大脑/人设与风格/0.IP人设/真人相片`

Default style: realistic, polished, personal-brand editorial look.

## Workflow

1. Build a profile reference set:
   - Automatically scan the default photo directory.
   - Always prefer `头像.JPG` as the primary face reference when it exists.
   - Select 3-5 complementary photos by resolution and orientation.
   - Convert HEIC files to temporary JPEG references before rendering.
   - Generate prompts and, when confirmed, render:
     - front face
     - left side face
     - right side face
     - half body
     - full body
     - gesture
2. Generate topic covers:
   - Read the profile reference set.
   - Use generated reference images first when available; otherwise use the selected source photos.
   - Generate multi-platform covers:
     - xhs: 4:5
     - wechat: 2.35:1
     - video: 9:16

## Commands

Build profile prompts only:

```bash
python3 /Users/aki/Development/code/aki-skills/skills/aki-personal-ip-cover/scripts/generate_personal_ip.py \
  build_profile \
  --out /absolute/path/to/output
```

Build profile and render images:

```bash
python3 /Users/aki/Development/code/aki-skills/skills/aki-personal-ip-cover/scripts/generate_personal_ip.py \
  build_profile \
  --out /absolute/path/to/output \
  --confirm
```

Generate topic cover prompts only:

```bash
python3 /Users/aki/Development/code/aki-skills/skills/aki-personal-ip-cover/scripts/generate_personal_ip.py \
  cover \
  --title "你的话题标题" \
  --profile /absolute/path/to/output/profile \
  --out /absolute/path/to/output/covers
```

Generate topic covers:

```bash
python3 /Users/aki/Development/code/aki-skills/skills/aki-personal-ip-cover/scripts/generate_personal_ip.py \
  cover \
  --title "你的话题标题" \
  --profile /absolute/path/to/output/profile \
  --out /absolute/path/to/output/covers \
  --confirm
```

## Options

- `--photo-dir`: source photo directory. Defaults to Aki's local真人相片 directory.
- `--out`: output directory.
- `--title`: topic title for cover generation.
- `--profile`: profile directory created by `build_profile`.
- `--max-photos`: number of source photos to auto-select, default 5.
- `--confirm`: actually render images. Without it, the script only writes prompts and metadata.
- `--image-provider`: currently `comfly` is the default because reference images are required.

## Outputs

Profile:

- `profile/selected_photos.json`
- `profile/prompts/*.md`
- `profile/images/front.png`
- `profile/images/left-side.png`
- `profile/images/right-side.png`
- `profile/images/half-body.png`
- `profile/images/full-body.png`
- `profile/images/gesture.png`
- `profile/profile-card.md`
- `metadata.json`

Covers:

- `covers/prompts/*.md`
- `covers/xhs/*.png`
- `covers/wechat/*.png`
- `covers/video/*.png`
- `covers/metadata.json`

## Notes

- Do not copy Aki's source photos into the repository.
- Do not hardcode API keys. Credentials must come from `/Users/aki/.config/ai/keys.env` or existing provider config.
- Prefer prompt-only first if the user is still checking the visual direction.
