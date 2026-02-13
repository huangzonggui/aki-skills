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
2. Append `references/constraints.md` and the shared style template `../aki-style-library/references/styles/手绘逻辑信息艺术设计师.md`.
3. Write a prompt file and generate the image with Comfly API.

## Options

- `--article`: Article markdown path (required)
- `--output`: Output image path (default when omitted: `imgs/handnote-cover.<YYYYmmdd-HHMMSS>.png`)
- `--prompt-out`: Prompt markdown output path (default: `imgs/prompts/handnote-cover.md`)
- `--title`: Override title text (default: first `#` heading)
- `--prompt-only`: Only write the prompt file, skip image generation
- `--overwrite`: Explicitly allow overwriting an existing output image path (default: do not overwrite)
- `--session-id`: Legacy option, ignored in Comfly API mode
- `--model`: Legacy option, ignored (model is locked to `nano-banana-pro`)

## Notes

- Do not use baoyu cover/xhs skills for this flow; keep full content density.
- Configure Comfly in `~/.config/comfly/config` (`COMFLY_API_KEY`, `COMFLY_API_BASE_URL` or `COMFLY_API_URL`).

## Resources

- High-density constraints: `references/constraints.md`
- Handnote style template: `../aki-style-library/references/styles/手绘逻辑信息艺术设计师.md`
- Generator script: `scripts/generate_handnote_cover.py`
