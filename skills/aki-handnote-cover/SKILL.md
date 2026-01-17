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

This writes a prompt to `imgs/prompts/handnote-cover.md` and generates `imgs/handnote-cover.png` next to the article.

## Workflow

1. Read the full article without summarizing.
2. Append `references/constraints.md` and the shared style template `../aki-style-library/references/styles/handnote.md`.
3. Write a prompt file and generate the image with Gemini Web.

## Options

- `--article`: Article markdown path (required)
- `--output`: Output image path (default: `imgs/handnote-cover.png`)
- `--prompt-out`: Prompt markdown output path (default: `imgs/prompts/handnote-cover.md`)
- `--title`: Override title text (default: first `#` heading)
- `--prompt-only`: Only write the prompt file, skip image generation
- `--session-id`: Gemini session ID (optional)
- `--model`: Gemini model id (optional)

## Notes

- Do not use baoyu cover/xhs skills for this flow; keep full content density.
- If Gemini is not logged in, run the login step in `baoyu-gemini-web` first.

## Resources

- High-density constraints: `references/constraints.md`
- Handnote style template: `../aki-style-library/references/styles/handnote.md`
- Generator script: `scripts/generate_handnote_cover.py`
