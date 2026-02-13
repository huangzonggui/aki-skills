---
name: aki-dense-handnote-series
description: Generate a high-density handnote-style multi-image series from a full article without summarizing; split by length to cover all content for image-text posts. Use when asked to turn an article into multiple dense handnote/infographic images.
---

# Aki Dense Handnote Series

Convert a full article into multiple dense handnote images that cover all content (no summarization). Best for image-text posts.

## Quick Start

```bash
python scripts/generate_handnote_series.py --article /path/to/article.md
```

## Options

- `--max-chars <int>`: Max characters per image (default: 1200). Increase for fewer images, decrease for more.
- `--output-dir <path>`: Output directory (default: `<article_dir>/imgs/handnote-series`)
- `--prompt-only`: Only write prompt files, skip image generation
- `--title <text>`: Override title text
- `--session-id <id>`: Legacy option, ignored in Comfly API mode
- `--model <id>`: Legacy option, ignored (model is locked to `nano-banana-pro`)

## Workflow

1. Read the full article without summarizing.
2. Split content by headings/paragraphs into chunks up to `--max-chars`.
3. For each chunk, build a prompt using:
   - `references/constraints.md`
   - `../aki-style-library/references/styles/手绘逻辑信息艺术设计师.md`
4. Write prompt files under `prompts/`, and generate one image per prompt.
5. Generate images through Comfly API (`nano-banana-pro`).

## Output Structure

```
<article_dir>/imgs/handnote-series/
|-- outline.md
|-- prompts/
|   |-- 01.md
|   |-- 02.md
|   `-- ...
|-- 01.png
|-- 02.png
`-- ...
```

## Notes

- This workflow prioritizes high information density; it intentionally overrides the low-density guidance in the base handnote style.
- Configure Comfly in `~/.config/comfly/config` (`COMFLY_API_KEY`, `COMFLY_API_BASE_URL` or `COMFLY_API_URL`).
- If you want to use another image generator, run with `--prompt-only` and feed the prompt files to your preferred tool.

## Resources

- High-density constraints: `references/constraints.md`
- Handnote style template: `../aki-style-library/references/styles/手绘逻辑信息艺术设计师.md`
- Generator script: `scripts/generate_handnote_series.py`
