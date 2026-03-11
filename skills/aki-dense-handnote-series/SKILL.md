---
name: aki-dense-handnote-series
description: Generate a high-density handnote-style image bundle (cover + logic-based series) from a full article without summarizing. Use when asked to turn an article into multiple dense handnote/infographic images.
---

# Aki Dense Handnote Series

Convert a full article into dense handnote images with logic-based pagination (no summarization). Best for image-text posts.

## Quick Start

```bash
python scripts/generate_handnote_bundle.py \
  --article /path/to/article.md \
  --cover-output /path/to/images/cover/cover_01.png \
  --series-output-dir /path/to/images/series \
  --prompts-output-dir /path/to/prompts \
  --outline-output /path/to/images/series/outline.md
```

## Options

- `--content-min-pages <int>`: Minimum content pages (default: 2, does not include cover)
- `--content-max-pages <int>`: Maximum content pages (default: 4, does not include cover)
- `--ending-policy adaptive|always|never`: Ending page policy (default: `adaptive`)
- `--logic-mode hybrid|rule|llm`: Page planning mode (default: `hybrid`)
- `--skip-cover`: Do not generate `cover_prompt` or cover image
- `--prompt-only`: Only write prompt files, skip image generation
- `--render`: Force rendering stage
- `--model <id>`: Override image model
- `--llm-model <id>`: Override fallback planner chat model
- `--render-series-limit <int>`: Only render the first N series pages (use `1` for low-cost validation with cover + first page)

## Workflow

1. Read the full article without summarizing.
2. Split content into logic units (heading/list/paragraph boundaries + role detection).
3. Plan content pages in range 2-4:
   - Rule-first grouping (hook/context/mechanism/evidence/risk/judgment/cta).
   - LLM fallback only when rule plan cannot satisfy page quality constraints.
4. Build one cover prompt + multiple series prompts using:
   - `references/constraints.md`
   - `../aki-handnote-cover/references/constraints.md`
   - `../aki-style-library/references/styles/手绘逻辑信息艺术设计师.md`
   - Current visual defaults:
     - pure white background
     - 48px edge-safe margin on 2K-class canvases
5. Enforce cover/series layout separation:
   - cover reuses `aki-handnote-cover` logic and keeps full-article density
   - series pages stay content-first and choose layout dynamically from the page logic, not a fixed template
6. Optionally render images through Comfly API.

## Output Structure

1. Cover image: `<...>/images/cover/cover_01.png`
2. Series images: `<...>/images/series/*.png`
3. Prompt files:
   - `<...>/prompts/cover_prompt.md`
   - `<...>/prompts/series_XX_prompt.md`
4. Outline: `<...>/images/series/outline.md`

## Notes

- This workflow prioritizes high information density; it intentionally overrides the low-density guidance in the base handnote style.
- Configure Comfly in `~/.config/comfly/config` (`COMFLY_API_KEY`, `COMFLY_API_BASE_URL` or `COMFLY_API_URL`).
- If you want to use another image generator, run with `--prompt-only` and feed the prompt files to your preferred tool.
- Long-term decisions: `references/decisions.md`

## Resources

- High-density constraints: `references/constraints.md`
- Handnote style template: `../aki-style-library/references/styles/手绘逻辑信息艺术设计师.md`
- Unified generator script: `scripts/generate_handnote_bundle.py`
