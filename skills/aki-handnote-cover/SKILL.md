---
name: aki-handnote-cover
description: Generate a single high-density handnote-style cover/infographic from a full article without summarizing or trimming content. Use when asked to convert an article into a dense hand-drawn note image or cover using the handnote template.
---

# Aki Handnote Cover

## Overview

Create a reusable workflow that combines a fixed high-density constraint block, the shared handnote style template, and the full article text to generate a single dense cover image.

## Quick Start

```bash
python scripts/generate_handnote_cover.py --article /path/to/article.md
```

This writes a prompt to `imgs/prompts/handnote-cover.md` and generates `imgs/handnote-cover.<YYYYmmdd-HHMMSS>.png` next to the article by default.
If you pass `--output`, it still avoids overwrite unless you also pass `--overwrite`.

## Workflow

1. Read the full article without summarizing.
   - Default behavior cleans obvious WeChat noise before composing prompt:
     - metadata lines (`作者`/`发布时间`/`原文链接`)
     - CTA/footer noise (`关注`/`点赞`/`在看`/`转发`/`秒追`/`点亮星标`)
     - reference-tail junk (`参考资料`后常见 URL + 引导语)
     - placeholder image lines (`![图片](640)` / `![Image n](...)`)
2. Append `references/constraints.md` and the shared style template `../aki-style-library/references/styles/手绘逻辑信息艺术设计师.md`.
   - Current visual defaults:
     - pure white background
     - 48px edge-safe margin on 2K-class canvases
3. Write a prompt file and generate the image with Comfly API.

## Options

- `--article`: Article markdown path (required)
- `--output`: Output image path (default when omitted: `imgs/handnote-cover.<YYYYmmdd-HHMMSS>.png`)
- `--prompt-out`: Prompt markdown output path (default: `imgs/prompts/handnote-cover.md`)
- `--title`: Override title text (default: first `#` heading)
- `--prompt-only`: Only write the prompt file, skip image generation
- `--raw-article`: Disable cleanup and use raw article text as-is
- `--overwrite`: Explicitly allow overwriting an existing output image path (default: do not overwrite)
- `--dump-payload`: 导出实际 Comfly 请求体 JSON（用于排查参数/提示词差异）
- `--dump-only`: 仅导出请求体，不发起生图 API 调用
- `--session-id`: Legacy option, ignored in Comfly API mode
- `--model`: Legacy option, ignored (set `COMFLY_IMAGE_MODEL` in `~/.config/comfly/config`)

## Notes

- Do not use baoyu cover/xhs skills for this flow; keep full content density.
- Configure Comfly in `~/.config/comfly/config` (`COMFLY_API_KEY`, `COMFLY_API_BASE_URL` or `COMFLY_API_URL`).

## Resources

- High-density constraints: `references/constraints.md`
- Handnote style template: `../aki-style-library/references/styles/手绘逻辑信息艺术设计师.md`
- Generator script: `scripts/generate_handnote_cover.py`

## 版本说明

- `v1.1.0` (2026-02-23)
  - 新增默认清洗：在拼接 prompt 前自动剔除微信文章常见噪音（作者/发布时间/原文链接、关注点赞引导、参考资料尾部、占位图行等）。
  - 新增开关：`--raw-article`，用于显式关闭清洗并保留原文输入。
