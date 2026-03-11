# aki-skills

English | [中文](./README.zh.md)

Aki's local skill collection for content workflows, publishing automation, and media tooling.

## Prerequisites

- Bun (`npx -y bun ...`) for TypeScript-based skills
- Python 3 for Python-based skills
- Google Chrome for browser automation skills

## Repository Layout

Each skill lives under `skills/<skill-name>/` and usually contains:

- `SKILL.md`: skill definition and usage instructions
- `scripts/`: executable scripts (TypeScript/Python/Shell)
- `references/` or `prompts/`: templates and documentation

## Typical Usage

```bash
# Fetch WeChat article content
npx -y bun skills/aki-wechat-fetcher/scripts/fetch.ts --url "<wechat-article-url>"

# Publish markdown to WeChat draft
npx -y bun skills/aki-post-to-wechat/scripts/wechat-browser.ts --markdown article.md --images ./images
```

## Core Skills

- `aki-content-pipeline-pro`: end-to-end content pipeline (sources -> notes -> platform outputs)
- `aki-context-to-html`: text/article to styled HTML and long-image assets
- `aki-post-to-wechat`: browser-first WeChat Official Account publishing
- `aki-wechat-api-imagepost`: API fallback path for WeChat publishing
- `aki-wechat-fetcher`: fetch WeChat official account articles
- `aki-image-article-video`: image/article to JianYing draft pipeline
- `aki-gemini-playwright-mcp`: Gemini web image generation via Playwright MCP
- `aki-gemini-web-curl`: Gemini web image generation via Chrome cookies + curl, with raw capture and ratio retries
- `aki-trendradar`: public-opinion monitoring and analysis

## Plugin Metadata

Plugin metadata is managed in [.claude-plugin/marketplace.json](./.claude-plugin/marketplace.json).

## Notes

- Marketplace metadata is defined in `.claude-plugin/marketplace.json`.
