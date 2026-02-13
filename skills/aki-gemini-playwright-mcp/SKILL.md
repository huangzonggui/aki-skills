---
name: aki-gemini-playwright-mcp
description: Generate images via Gemini web using Playwright MCP (free browser automation). Use when you need image generation without paid APIs, when Gemini cookie sync is unstable, or when you want to reuse a logged-in browser profile.
---

# Aki Gemini Playwright MCP

Automate Gemini web image generation using Playwright, exposed as an MCP tool. This avoids API costs and is more stable than cookie-sync flows.

## Quick Start

1) Install deps (one-time):
```bash
cd /Users/aki/Development/code/aki-skills/skills/aki-gemini-playwright-mcp/scripts
bun install
npx playwright install chromium
```

2) Start MCP server:
```bash
bun /Users/aki/Development/code/aki-skills/skills/aki-gemini-playwright-mcp/scripts/mcp-server.ts
```

3) Log in once (first run):
- A Chromium profile is stored at `~/Library/Application Support/baoyu-skills/gemini-mcp/chrome-profile`.
- Open `https://gemini.google.com/app` and log in.

4) Call MCP tool `generateGeminiImage` with:
- `prompt` (required)
- `outputPath` (optional)

## MCP Tool

`generateGeminiImage`
- **prompt**: string (required)
- **outputPath**: string (optional, default `./gemini-image.png`)
- **profileDir**: string (optional)
- **headless**: boolean (optional)
- **timeoutMs**: number (optional, default 180000)
- **keepOpen**: boolean (optional)

## CLI Fallback (No MCP)

```bash
bun /Users/aki/Development/code/aki-skills/skills/aki-gemini-playwright-mcp/scripts/gemini-playwright.ts \
  --prompt "生成一张彩绘手绘风格的高信息密度封面" \
  --out "/path/to/output.png"
```

## Notes
- Keep the Gemini tab active for best stability.
- If the composer is not ready, the tool will wait and then error with a login hint.

## References
- `references/workflow.md`
- `references/troubleshooting.md`
