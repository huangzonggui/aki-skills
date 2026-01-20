---
name: aki-context-to-html
description: Convert article/text to styled HTML with smart highlight analysis and export as 3:4 PNG slices. Fixed text distortion in slicing by using proper canvas scaling. Use when asked to create article HTML, social media long images, or content beautifier.
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
| Modern UI Layout | Dark control panel + light content area with elegant typography |
| Progress Tracking | Shows export progress with toast notifications |

## Script Reference

| Script | Purpose |
|--------|---------|
| `scripts/generate-html.ts` | Main script: generates HTML from input |
| `scripts/template.html` | HTML template with embedded styling and slicing logic |

## Visual Design

### Typography
- **Title**: Noto Serif SC (Serif font for elegance)
- **Body**: Inter/system-ui (Clean sans-serif)
- **Code**: JetBrains Mono/Fira Code

### Color System
- **Primary**: Purple gradient (`#667eea` → `#764ba2`)
- **Highlights**:
  - Yellow: Core insights (`#ffeb3b`)
  - Pink: Products/pain points (`#ff80ab`)
  - Green: Benefits (`#b9f6ca`)
  - Blue: Actions/data (`#80d8ff`)

### Layout
- Section titles: Left purple border accent
- Lists: Purple dot markers
- Cards: White with deep shadow
- Background: Purple gradient

## Slicing Algorithm (FIXED)

The slicing uses a **fixed-width, variable-height** approach to prevent text distortion:

```
┌─────────────────────────┐
│  Canvas: 1080 × variable │  ← Maintain aspect ratio per slice
│  Scale: 2x for retina    │
└─────────────────────────┘

Instead of stretching content:
1. Render full content at target width (1080px)
2. Calculate slice height based on 3:4 ratio (1440px)
3. Slice at exact pixel boundaries
4. Add page numbers to each slice
```

**Key Fix**: Set explicit canvas dimensions before drawing, don't rely on CSS scaling.

## Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `<input>` | Input file path (markdown/text) | Required |
| `--output <path>` | Output HTML path | `<input-dir>/article.html` |
| `--ratio <ratio>` | Aspect ratio: `3:4` or `3:5` | `3:4` |
| `--width <px>` | Target width in pixels | `1080` |
| `--title <text>` | Override article title | From frontmatter/H1 |

## Resources

- **Usage Guide**: `references/usage.md`
- **Template**: `scripts/template.html`
- **Examples**: `references/examples/`

## Troubleshooting

- **Text looks compressed**: Make sure canvas has explicit width/height set before `drawImage()`
- **Fonts not loading**: Check Google Fonts CDN access or use local fonts
- **Slicing cuts text mid-line**: Report bug - should split by block elements only
