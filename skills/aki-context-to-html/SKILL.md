---
name: aki-context-to-html
description: Convert article/text to styled HTML with AI-powered smart formatting. Uses GLM/OpenAI compatible APIs. Supports 3:4/3:5 PNG export with block-level slicing. Use when asked to create article HTML, social media long images, or content beautifier.
---

# Aki Context to HTML

Convert article/text to styled HTML with AI-powered smart formatting and export as multiple PNG slices.

## Quick Start

```bash
# Set your API key (GLM by default)
export CLOUD_CODE_API_KEY="your-api-key-here"

# Generate HTML from markdown
npx -y bun ${SKILL_DIR}/scripts/generate-html.ts input.md

# With custom output path
npx -y bun ${SKILL_DIR}/scripts/generate-html.ts input.md --output ./output/article.html
```

> **Note**: `${SKILL_DIR}` represents this skill's installation directory. Agent replaces with actual path at runtime.

## Features

| Feature | Description |
|---------|-------------|
| AI Smart Formatting | Uses LLM (GLM by default) to analyze content and apply semantic HTML |
| Multiple Highlight Styles | `<mark>` (yellow), `<em>` (red), `<strong>` (bold), `<blockquote>` (blue border) |
| Flexible API Support | GLM, OpenAI, or any OpenAI-compatible API |
| Block-Level Slicing | Splits by HTML elements, not pixels - no cut text lines |
| Modern UI Layout | Dark control panel + pure white content area |
| Progress Tracking | Shows export progress with toast notifications |

## Script Reference

| Script | Purpose |
|--------|---------|
| `scripts/generate-html.ts` | Main script: generates HTML from input using LLM |
| `scripts/template.html` | HTML template with embedded styling and slicing logic |

## Visual Design (Reference: modern-article-styler)

### Typography
- **H1 Title**: Noto Serif SC, 36px, 800 weight, black border-bottom
- **H2 Section**: Times New Roman or Noto Serif SC, 32px, red left border (12px)
- **H3 Subsection**: 24px, bold, dark gray
- **Body**: Inter, 20px, line-height 1.8

### Color System
- **Background**: Pure white (`#ffffff`)
- **H1 Border**: Black (`#000000`)
- **H2 Border**: Red (`#e53e3e`)
- **Blockquote Border**: Blue (`#4a9eff`)
- **Highlights**:
  - `<mark>`: Yellow background (`#fff59d`) + orange underline (`#ff9800`)
  - `<em>`: Red (`#e53e3e`), bold
  - `<strong>`: Black (`#000000`), 800 weight

### Blockquote Style
- Left border: 8px blue (`#4a9eff`)
- Background: Light blue (`rgba(74, 158, 255, 0.05)`)
- Italic text
- 30px font size

## API Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CLOUD_CODE_API_KEY` | API key (GLM/OpenAI) | **Required** |
| `CLOUD_CODE_API_URL` | API endpoint | GLM API |
| `CLOUD_CODE_MODEL` | Model name | `glm-4-flash` |

### Alternative Variables (for compatibility)

```
GLM_API_KEY, OPENAI_API_KEY, API_KEY
GLM_API_URL, OPENAI_API_URL
GLM_MODEL, MODEL
```

### Supported APIs

| API | API URL | Model |
|-----|---------|-------|
| **GLM (智谱)** | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | `glm-4-flash` |
| **OpenAI** | `https://api.openai.com/v1/chat/completions` | `gpt-4o-mini` |
| **DeepSeek** | `https://api.deepseek.com/v1/chat/completions` | `deepseek-chat` |

## Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `<input>` | Input file path (markdown/text) | Required |
| `--output <path>` | Output HTML path | `<input-dir>/article.html` |
| `--ratio <ratio>` | Aspect ratio: `3:4` or `3:5` | `3:4` |
| `--width <px>` | Target width in pixels | `600` |
| `--title <text>` | Override article title | From frontmatter/H1 |
| `--api-url <url>` | Override API URL | GLM API |
| `--api-key <key>` | Override API key | From env |
| `--model <name>` | Override model name | `glm-4-flash` |

### Output Dimensions

| Ratio | Width | Height | Use Case |
|-------|-------|--------|----------|
| 3:4 | 600px | 800px | Standard social media |
| 3:5 | 600px | 1000px | Taller format |

## Slicing Algorithm (BLOCK-LEVEL)

The slicing uses **block-level element splitting** to prevent cutting text:

```
Target: 600 × 800px (3:4) or 600 × 1000px (3:5)

Block-level splitting:
1. Measure each block element (h1, h2, h3, p, blockquote, etc.)
2. Accumulate blocks until target height
3. If next block exceeds, start new slice
4. Never cut within a block
```

**Key**: Uses hidden staging div to measure element heights before slicing.

## Resources

- **Usage Guide**: `references/usage.md`
- **Template**: `scripts/template.html`
- **Reference Code**: `/Users/aki/Development/code/modern-article-styler-&-exporter` (for HTML style reference)

## Troubleshooting

- **API Key not found**: Set `CLOUD_CODE_API_KEY` environment variable
- **API request failed**: Check API key and URL are correct
- **Text looks compressed**: Should be fixed - width is 600px by default
- **Background not white**: Should be fixed - pure white background is default
- **Text gets cut mid-line**: Should be fixed - now uses block-level slicing
