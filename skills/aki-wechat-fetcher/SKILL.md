---
name: aki-wechat-fetcher
description: Fetch WeChat Official Account articles using Playwright browser automation. No API key required. Extract article content, title, author, publish time, and images to markdown format.
---

# Aki WeChat Fetcher

Fetch WeChat Official Account (微信公众号) articles directly using Playwright browser automation. No third-party API required.

## Quick Start

```bash
# Fetch single article
npx -y bun ${SKILL_DIR}/scripts/fetch.ts "https://mp.weixin.qq.com/s/xxxxx"

# Fetch to specific output
npx -y bun ${SKILL_DIR}/scripts/fetch.ts "https://mp.weixin.qq.com/s/xxxxx" --output "./articles"

# Fetch without images
npx -y bun ${SKILL_DIR}/scripts/fetch.ts "https://mp.weixin.qq.com/s/xxxxx" --no-images
```

## Features

- **No API Key Required** - Uses browser automation to fetch articles directly
- **Full Content Extraction** - Title, author, publish time, content, images
- **Markdown Output** - Clean markdown format with image references
- **Image Download** - Optionally download article images locally
- **Batch Support** - Fetch multiple articles from a list

## Script Reference

| Script | Purpose |
|--------|---------|
| `scripts/fetch.ts` | Main fetch script |
| `scripts/batch.ts` | Batch fetch from URL list |

## Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `<url>` | WeChat article URL | Required |
| `--output <path>` | Output directory | `./output` |
| `--no-images` | Skip image download | false |
| `--timeout <ms>` | Page load timeout | 30000 |
| `--headless` | Run headless mode | true |
| `--profile <path>` | Chrome profile path | - |

## Output Format

```
output/
  <timestamp>_<title>.md
  images/
    <timestamp>_<cover>.jpg
    <timestamp>_img_1.jpg
    ...
```

## Example

```bash
# Fetch with custom output
npx -y bun ${SKILL_DIR}/scripts/fetch.ts \
  "https://mp.weixin.qq.com/s/7pX7nZwLV5I-KcHVmGLN_w" \
  --output "./我的文章" \
  --timeout 60000
```

## Notes

- First run may be slower as Playwright downloads Chromium
- Some articles may require login (use `--profile` with your Chrome profile)
- Public articles work without login
- Images are referenced relative to the markdown file

## MCP Tool (Optional)

If running as MCP server:

`fetchWechatArticle`
- **url**: string (required) - WeChat article URL
- **outputPath**: string (optional) - Output directory
- **downloadImages**: boolean (optional) - Download images locally
