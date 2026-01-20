---
name: aki-context-to-html
description: Convert article/text to styled HTML with smart highlight analysis and export as 3:4 PNG slices. Uses 600px width with block-level slicing for optimal readability. Pure white background. Use when asked to create article HTML, social media long images, or content beautifier.
---

# Aki Context to HTML

Convert article/text to styled HTML with AI-powered smart formatting (bold, highlights) and export as multiple 3:4 PNG slices.

## Quick Start

```bash
# Generate HTML from markdown/text
npx -y bun ${SKILL_DIR}/scripts/generate-html.ts input.md

# With custom output path
npx -y bun ${SKILL_DIR}/scripts/generate-html.ts input.md --output ./output/article.html

# With custom aspect ratio (3:4 or 3:5)
npx -y bun ${SKILL_DIR}/scripts/generate-html.ts input.md --ratio 3:5
```

> **Note**: `${SKILL_DIR}` represents this skill's installation directory. Agent replaces with actual path at runtime.

## Features

| Feature | Description |
|---------|-------------|
| AI Smart Formatting | Analyzes content and applies bold/highmark automatically |
| Multiple Highlight Colors | Yellow (key points), Pink (products), Green (benefits), Blue (actions) |
| 3:4 / 3:5 PNG Export | Slices HTML into multiple images without text distortion |
| Block-Level Slicing | Splits by HTML elements, not pixels - no cut text lines |
| Modern UI Layout | Dark control panel + pure white content area |
| Progress Tracking | Shows export progress with toast notifications |

## Script Reference

| Script | Purpose |
|--------|---------|
| `scripts/generate-html.ts` | Main script: generates HTML from input |
| `scripts/template.html` | HTML template with embedded styling and slicing logic |

## Visual Design

### Typography (per ContextToHtml requirements)
- **Title**: Noto Serif SC (宋体, Serif font for elegance)
- **Body**: Inter (Clean sans-serif)
- **Code**: JetBrains Mono

### Color System
- **Background**: Pure white (`#ffffff`) for optimal readability
- **Highlights**:
  - Yellow: Core insights (`#fbbf24` + orange underline)
  - Pink: Products/pain points (`#f472b6`)
  - Green: Benefits (`#86efac`)
  - Blue: Actions/data (`#60a5fa`)

### Layout
- Section titles: Left red border (`#ef4444`)
- Lists: Purple dot markers (`#667eea`)
- Cards: White with deep shadow
- Background: **Pure white** (not purple gradient)

## Slicing Algorithm (BLOCK-LEVEL)

The slicing uses **block-level element splitting** to prevent cutting text:

```
┌─────────────────────────┐
│  Target: 600 × 800px     │  ← 3:4 ratio
│  Per requirements:       │
│  - Width: 600px (fixed)  │
│  - Height: 800px (3:4)   │
│  - Height: 1000px (3:5)  │
└─────────────────────────┘

Block-level splitting:
1. Measure each block element (h2, p, ul, etc.)
2. Accumulate blocks until target height
3. If next block exceeds, start new slice
4. Never cut within a block
```

**Key**: Uses hidden staging div to measure element heights before slicing.

## Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `<input>` | Input file path (markdown/text) | Required |
| `--output <path>` | Output HTML path | `<input-dir>/article.html` |
| `--ratio <ratio>` | Aspect ratio: `3:4` or `3:5` | `3:4` |
| `--width <px>` | Target width in pixels | `600` |
| `--title <text>` | Override article title | From frontmatter/H1 |

### Output Dimensions

| Ratio | Width | Height | Use Case |
|-------|-------|--------|----------|
| 3:4 | 600px | 800px | Standard social media |
| 3:5 | 600px | 1000px | Taller format |

## Resources

- **Usage Guide**: `references/usage.md`
- **Template**: `scripts/template.html`

## Smart Highlighting Rules

The skill automatically applies highlights based on content analysis:

| Color | Pattern | Example |
|-------|---------|---------|
| Yellow (`<mark>`) | Core insights | "本质上..."、"根本性的变化..." |
| Red (`<em>`) | Emphasized words | "最重要"、"核心"、"10倍" |
| Pink | Product names | "飞书录音豆"、"WhisperFlow" |
| Green | Benefits | "锻炼..."、"提升..."、"培养..." |
| Blue | Action items | "从现在开始..."、"我的建议是..." |

To add manual highlights, use markdown:
- `==text==` for yellow highlight
- `**text**` for bold
- `*text*` for red italic

## Troubleshooting

- **Text looks compressed**: Should be fixed - width is now 600px by default
- **Background not white**: Should be fixed - pure white background is now default
- **Text gets cut mid-line**: Should be fixed - now uses block-level slicing
- **Fonts not loading**: Check Google Fonts CDN access or use local fonts
