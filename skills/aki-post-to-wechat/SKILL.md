---
name: aki-post-to-wechat
description: Post content to WeChat Official Account. Supports both long-form article posting (文章) and image-text posting (图文), reusing baoyu-post-to-wechat's stable automation flow.
---

# Aki Post to WeChat (文章 + 图文)

Post content to WeChat Official Account, including:
- Article posting (文章) with `aki-context-to-html` styling pipeline.
- Image-text posting (图文) with baoyu's stable browser automation flow.

This skill keeps the proven article publishing automation flow from `baoyu-post-to-wechat`, but removes theme-system styling (`default/grace/simple/huasheng`) and uses `aki-context-to-html` as the style generation backend.

## Script Directory

All scripts are in the `scripts/` subdirectory.

| Script | Purpose |
|--------|---------|
| `scripts/wechat-browser.ts` | Image-text posting automation (图文) |
| `scripts/wechat-article.ts` | Main article posting automation |
| `scripts/md-to-wechat-context.ts` | Markdown -> context-to-html -> WeChat-ready HTML |
| `scripts/cdp.ts` | Chrome CDP helpers |
| `scripts/copy-to-clipboard.ts` | Copy HTML/image to system clipboard |
| `scripts/paste-from-clipboard.ts` | Real paste keystroke helper |

## Quick Usage

```bash
# Image-text posting (图文)
npx -y bun ./scripts/wechat-browser.ts --markdown post.md --images ./imgs --submit

# Preview/edit in WeChat editor (will still save draft in current script behavior)
npx -y bun ./scripts/wechat-article.ts --markdown article.md

# Save draft
npx -y bun ./scripts/wechat-article.ts --markdown article.md --submit

# Optional overrides
npx -y bun ./scripts/wechat-article.ts --markdown article.md --author "Aki聊AI" --summary "摘要"
```

## Parameters

| Parameter | Description |
|-----------|-------------|
| `--markdown <path>` | Markdown file path (recommended) |
| `--html <path>` | Pre-rendered HTML file |
| `--title <text>` | Override title |
| `--author <name>` | Override author |
| `--summary <text>` | Override summary |
| `--skip-title` | Skip auto-filling title |
| `--manual-paste` | Pause for manual paste before image insertion |
| `--submit` | Save as draft |
| `--profile <dir>` | Chrome profile directory |

## Style Backend

When `--markdown` is used:
1. Replace markdown images with placeholders.
2. Call `aki-context-to-html/scripts/generate-html.ts` to generate styled HTML.
   - Final HTML is saved next to the markdown file as `<name>.wechat.html` by default.
3. Copy HTML with baoyu's stable strategy:
   - Try `copy-to-clipboard` rich HTML first.
   - Fallback to opening local HTML and copying selected `#output`.
4. Paste into WeChat editor.
5. Replace placeholders with real images in-place.

## Context-to-HTML Path Resolution

`md-to-wechat-context.ts` resolves `aki-context-to-html` in this order:
1. `AKI_CONTEXT_TO_HTML_DIR`
2. `CONTEXT_TO_HTML_DIR`
3. `/Users/aki/.codex/skills/aki-context-to-html`
4. `/Users/aki/Development/code/aki-skills/skills/aki-context-to-html`
5. `/Users/aki/.claude/skills/aki-context-to-html`
6. `~/.codex/skills/context-to-html`

If not found, set one of the two env vars.

## Reference

- `references/article-posting.md`
- `references/image-text-posting.md`
