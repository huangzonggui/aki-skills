---
name: aki-post-to-wechat-browser
description: Browser-first publishing for WeChat Official Account posting (文章 + 图文). Use this skill by default when users ask to publish via web UI automation, save drafts, or avoid API/IP whitelist friction. API skill is fallback only when user explicitly asks for API mode.
---

# Aki Post to WeChat (文章 + 图文)

> 默认策略：优先使用浏览器版（本 skill）。只有用户明确要求 API，或浏览器链路不可用时，才切到 `aki-post-to-wechat`（API版）。

Post content to WeChat Official Account, including:
- Article posting (文章) with `aki-context-to-html` styling pipeline.
- Image-text posting (图文) with independent browser automation.

## 模式锁定规则（防混淆）

- 用户说“图文 / 贴图 / 发图 / 多图”：
  - 固定使用 `scripts/wechat-browser.ts`（图文链路）。
  - 不得自动改成 `wechat-article.ts`。
- 用户说“文章 / 长文发布 / Markdown文章”：
  - 才使用 `scripts/wechat-article.ts`。
- 遇到排版问题时：
  - 先在当前模式内修复；
  - 若必须切换模式，先获得用户明确确认。

## 执行前模式确认输出模板

在执行前先输出 3 行确认（可审计）：

```text
用户意图=图文
脚本=wechat-browser.ts
禁止回退=文章链路
```

图文命令建议固定带上意图参数：

```bash
npx -y bun ./scripts/wechat-browser.ts --intent imagepost --markdown post.md --images ./imgs --submit
```

贴图默认行为（重要）：
- `--intent imagepost` 下，`--markdown` 默认只提取标题，不自动把 markdown 正文灌进内容编辑器。
- 只有显式传 `--content`，或显式加 `--with-markdown-content`，才会写正文。
- 纯贴图发布优先使用 `--title + --images`。

This skill provides independent browser automation for WeChat publishing, using `aki-context-to-html` as the style generation backend.

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
npx -y bun ./scripts/wechat-browser.ts --intent imagepost --markdown post.md --images ./imgs --submit

# Pure imagepost: title + images only
npx -y bun ./scripts/wechat-browser.ts --intent imagepost --title "标题" --images ./imgs --submit

# Only if you explicitly want markdown body pasted too
npx -y bun ./scripts/wechat-browser.ts --intent imagepost --markdown post.md --images ./imgs --with-markdown-content --submit

# Preview/edit in WeChat editor (will still save draft in current script behavior)
npx -y bun ./scripts/wechat-article.ts --markdown article.md

# Save draft
npx -y bun ./scripts/wechat-article.ts --markdown article.md --submit

# Save draft with explicit part-guide style
npx -y bun ./scripts/wechat-article.ts --markdown article.md --style part-guide --submit

# Optional overrides
npx -y bun ./scripts/wechat-article.ts --markdown article.md --author "Aki聊AI" --summary "摘要"
```

## Parameters

| Parameter | Description |
|-----------|-------------|
| `--markdown <path>` | Markdown file path (recommended) |
| `--html <path>` | Pre-rendered HTML file |
| `--title <text>` | Override title |
| `--style <name>` | Markdown 发布时指定 `aki-context-to-html` 样式，如 `part-guide` / `classic` |
| `--author <name>` | Override author |
| `--summary <text>` | Override summary |
| `--skip-title` | Skip auto-filling title |
| `--manual-paste` | Pause for manual paste before image insertion |
| `--submit` | Save as draft |
| `--profile <dir>` | Chrome profile directory |
| `--profile-name <name>` | Publisher profile name（默认 `zimeiti-publisher`，一般可不传） |

发布专用 profile 约定（推荐）：
- 不使用系统 `Default` 目录做自动化发布。
- 使用固定 profile 名称长期复用登录态与指纹。
- 默认固定名称：`zimeiti-publisher`（不传参数时自动使用）。
- 脚本会复用同 profile 的现有 Chrome 会话；若会话已存在，不会重复创建新环境。

Pre-submit settings policy (图文):
- Default ON when `--submit`: 原创/创作来源/赞赏/广告/合集 会自动尝试设置。
- `--skip-pre-submit-settings` is blocked by default to avoid accidental misses.
- To explicitly allow skipping (troubleshooting only), set `WECHAT_ALLOW_SKIP_PRE_SUBMIT=1`.

## Style Backend

When `--markdown` is used:
1. Replace markdown images with placeholders.
2. Call `aki-context-to-html/scripts/generate-html.ts` to generate styled HTML.
   - Final HTML is saved next to the markdown file as `<name>.wechat.html` by default.
3. Copy HTML with independent strategy:
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
