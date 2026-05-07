---
name: aki-handnote-cover
description: Generate a single high-density handnote-style cover/infographic from a full article without summarizing or trimming content. Use when asked to convert an article into a dense hand-drawn note image or cover using the handnote template.
---

# Aki Handnote Cover

## Overview

Create a reusable workflow that combines a fixed high-density constraint block, the shared handnote style template, and the full article text to generate a single dense cover prompt. This skill writes the prompt first, then renders through Comfly AI when image output is requested.

## Quick Start

```bash
python scripts/generate_handnote_cover.py --article /path/to/article.md
```

This writes a prompt to `imgs/prompts/handnote-cover.md` and stops before rendering.

To generate the cover image with Comfly AI:

```bash
python scripts/generate_handnote_cover.py \
  --article /path/to/article.md \
  --output /path/to/imgs/handnote-cover.png \
  --paid-api-fallback \
  --image-provider comfly
```

If you pass `--output`, the script still avoids overwrite unless you also pass `--overwrite`.

## Workflow

1. Read the full article without summarizing.
   - Default behavior cleans obvious WeChat noise before composing prompt:
     - metadata lines (`作者`/`发布时间`/`原文链接`)
     - CTA/footer noise (`关注`/`点赞`/`在看`/`转发`/`秒追`/`点亮星标`)
     - source/self-media tail noise (`来源`/`作者`/`编辑`/`记者`/`转载`/`某某解读`/`敬请留意`/`欢迎关注`)
     - bare source links and URL-only lines
     - reference-tail junk (`参考资料`后常见 URL + 引导语)
     - placeholder image lines (`![图片](640)` / `![Image n](...)`)
2. Append `references/constraints.md` and the shared style template `../aki-style-library/references/styles/手绘逻辑信息艺术设计师.md`.
   - Current visual defaults:
     - pure white background
     - 48px edge-safe margin on 2K-class canvases
     - exclude third-party media/blogger names, logos, bylines, account handles, QR codes, watermarks, domains, and raw URLs unless they are the article's primary subject
3. Write a prompt file.
4. If image output is requested, render with Comfly AI by passing `--paid-api-fallback --image-provider comfly`.

## Options

- `--article`: Article markdown path (required)
- `--output`: Target image path for Comfly rendering (default when omitted: `imgs/handnote-cover.<YYYYmmdd-HHMMSS>.png`)
- `--prompt-out`: Prompt markdown output path (default: `imgs/prompts/handnote-cover.md`)
- `--title`: Override title text (default: first `#` heading)
- `--prompt-only`: Only write the prompt file, skip paid API generation (default behavior; kept for compatibility)
- `--paid-api-fallback`: Render after prompt creation.
- `--image-provider`: Image provider for rendering. Use `comfly` for Comfly AI.
- `--raw-article`: Disable cleanup and use raw article text as-is
- `--overwrite`: Explicitly allow overwriting an existing output image path (default: do not overwrite)
- `--dump-payload`: 导出实际 Comfly 请求体 JSON（用于排查参数/提示词差异）
- `--dump-only`: 仅导出请求体，不发起生图 API 调用
- `--session-id`: Legacy option, ignored in Comfly API mode
- `--model`: Legacy option, ignored (set `COMFLY_IMAGE_MODEL` in `/Users/aki/.config/ai/keys.env`)

## Notes

- Do not use baoyu cover/xhs skills for this flow; keep full content density.
- Rendering should use Comfly AI.
- Configure Comfly in `/Users/aki/.config/ai/keys.env` (`COMFLY_API_KEY`, `COMFLY_API_BASE_URL` or `COMFLY_API_URL`, `COMFLY_IMAGE_MODEL`) for image generation.
- When article text contains source attribution or self-media promo tails, treat them as noise for cover generation rather than content that should appear in the image.

## Resources

- High-density constraints: `references/constraints.md`
- Handnote style template: `../aki-style-library/references/styles/手绘逻辑信息艺术设计师.md`
- Generator script: `scripts/generate_handnote_cover.py`

## 版本说明

- `v1.3.1` (2026-04-28)
  - 删除旧的本地 CLI 生图说明。
  - 明确封面图由 Comfly AI 渲染：`--paid-api-fallback --image-provider comfly`。
- `v1.3.0` (2026-04-28)
  - 默认只生成 prompt，不再自动调用 Comfly/OpenRouter。
  - 新增显式付费渲染开关。
- `v1.2.0` (2026-04-24)
  - 新增封面安全规则：禁止生成与主话题无关的第三方媒体名、自媒体/博主名称、作者/编辑署名、账号名、二维码、水印、logo、域名、URL 等来源归属信息。
  - 新增默认清洗：自动剔除 `某某解读`、`敬请留意`、来源署名和裸链等常见媒体尾巴，避免误带入封面。
- `v1.1.0` (2026-02-23)
  - 新增默认清洗：在拼接 prompt 前自动剔除微信文章常见噪音（作者/发布时间/原文链接、关注点赞引导、参考资料尾部、占位图行等）。
  - 新增开关：`--raw-article`，用于显式关闭清洗并保留原文输入。
