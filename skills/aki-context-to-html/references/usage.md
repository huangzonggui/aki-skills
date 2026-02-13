# Aki Context to HTML - Usage Guide

## Overview

This skill converts articles/text to styled HTML with smart AI-powered formatting and exports as multiple PNG slices.
It uses Comfly Chat Completions (Gemini 3 Pro Preview Thinking by default).

## Quick Start

```bash
cd /Users/aki/Development/code/aki-skills/skills/aki-context-to-html

export COMFLY_API_KEY="your-api-key"
npx -y bun scripts/generate-html.ts /path/to/article.md
```

## Workflow

### 1. Generate HTML

Run the script to convert your article to styled HTML:

```bash
npx -y bun scripts/generate-html.ts article.md
```

This creates `article.html` in the same directory as the input file.

### 2. Open in Browser

Open the generated HTML file in your browser:

```bash
open article.html  # macOS
start article.html  # Windows
xdg-open article.html  # Linux
```

### 3. Configure & Export

In the browser:

1. **Select Ratio**: Choose 3:4 or 3:5 aspect ratio
2. **Preview**: Check the article preview on the right
3. **Export PNG**: Click "导出 PNG 图片" to download all slices
4. **Download HTML**: Click "下载 HTML 源码" to save the source

## Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `<input>` | Input markdown file | Required |
| `--output <path>` | Output HTML path | `<input-dir>/article.html` |
| `--ratio <ratio>` | Aspect ratio (3:4 or 3:5) | 3:4 |
| `--width <px>` | Target width in pixels | 1080 |
| `--title <text>` | Override article title | From frontmatter |
| `--api-url <url>` | Override API URL | Comfly chat completions |
| `--api-key <key>` | Override API key | From env |
| `--model <name>` | Override model name | `gemini-3-pro-preview-thinking-*` |

### Examples

```bash
# Basic usage
npx -y bun scripts/generate-html.ts article.md

# Custom output path
npx -y bun scripts/generate-html.ts article.md --output ./dist/article.html

# 3:5 ratio for taller images
npx -y bun scripts/generate-html.ts article.md --ratio 3:5

# Higher resolution (1400px width)
npx -y bun scripts/generate-html.ts article.md --width 1400

# Custom title
npx -y bun scripts/generate-html.ts article.md --title "My Custom Title"
```

## Markdown Formatting

The script supports standard markdown with additional highlight syntax:

| Syntax | Output |
|--------|--------|
| `**bold**` | **Bold text** |
| `*italic*` | *Italic text* |
| `` `code` `` | `Inline code` |
| `==highlight==` | <mark>Highlighted text</mark> |
| `# H1` | Article title (extracted) |
| `## H2` | Section heading with red border |
| `> quote` | Blockquote with left border |
| `- item` | Unordered list item |
| `1. item` | Ordered list item |

## Frontmatter

You can add frontmatter to your markdown:

```yaml
---
title: My Custom Title
cover_image: ./cover.jpg
---
```

## Smart Formatting (Manual)

Apply different highlight colors by adding HTML classes:

```html
<span class="highlight">Yellow highlight - Core insights</span>
<span class="highlight-pink">Pink highlight - Products/pain points</span>
<span class="highlight-green">Green highlight - Benefits</span>
<span class="highlight-blue">Blue highlight - Actions/data</span>
```

## Output Structure

```
<input-directory>/
├── article.html          # Generated HTML file
├── article_01.png        # Exported PNG slices
├── article_02.png
└── ...
```

## Troubleshooting

### Text looks compressed/distorted

This should be **fixed** in the current version. The canvas now uses explicit dimensions before drawing, preventing text compression.

If you still see issues:
1. Clear browser cache
2. Try a different browser
3. Check console for errors

### Fonts not loading

- Check internet connection (Google Fonts CDN)
- Use local fonts by modifying `template.html`

### Export fails

1. Check browser console for errors
2. Ensure `html2canvas` is loaded (check network tab)
3. Try reducing image width: `--width 900`

### API errors

- Set `COMFLY_API_KEY` in your environment
- Optional: set `COMFLY_API_BASE_URL` if you use a custom Comfly gateway

### Too many/few slices

- **Too many**: Increase `--width` (e.g., 1200 or 1400)
- **Too few**: Decrease `--width` (e.g., 900 or 800)
- **Change ratio**: Use `--ratio 3:5` for taller slices

## Technical Details

### Slicing Algorithm (FIXED)

The new implementation fixes text distortion by:

1. **Setting explicit canvas dimensions** before drawing:
   ```javascript
   canvas.width = CONFIG.targetWidth * CONFIG.scale;
   canvas.height = contentArea.offsetHeight * CONFIG.scale;
   ```

2. **Rendering at target width** (not relying on CSS):
   ```javascript
   html2canvas(contentArea, {
       width: CONFIG.targetWidth,
       height: contentArea.offsetHeight,
       scale: 1,  // Use our own scale
       onclone: (doc) => {
           clonedContent.style.width = `${CONFIG.targetWidth}px`;
       }
   })
   ```

3. **Drawing with proper scale**:
   ```javascript
   ctx.scale(CONFIG.scale, CONFIG.scale);
   ctx.drawImage(htmlCanvas, 0, 0, CONFIG.targetWidth, htmlCanvas.height);
   ```

### File Structure

```
aki-context-to-html/
├── SKILL.md                 # Skill definition
├── scripts/
│   ├── generate-html.ts     # Main TypeScript script
│   └── template.html        # HTML template with slicing logic
└── references/
    └── usage.md             # This file
```

## Integration with Other Skills

This skill works well with:

- **aki-handnote-cover**: Generate cover images
- **aki-style-library**: Use consistent visual styles
- **baoyu-post-to-wechat**: Post to WeChat after export
