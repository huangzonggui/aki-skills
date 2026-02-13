# Aki WeChat Article Posting

## Goal

Publish markdown to WeChat Official Account with:
- Context-to-HTML generated styling
- Stable CDP-based editor automation
- Placeholder-based image replacement

## Command

```bash
npx -y bun ./scripts/wechat-article.ts --markdown ./article.md --submit
```

## Flow

1. Parse markdown title/author/summary.
2. Replace markdown image syntax with placeholders.
3. Generate styled HTML through `aki-context-to-html`.
   - Output HTML defaults to `<markdown_dir>/<markdown_name>.wechat.html`.
4. Copy HTML using baoyu-compatible strategy:
   - Prefer `copy-to-clipboard` rich HTML.
   - Fallback: open local HTML and copy selected `#output`.
5. Paste HTML into WeChat article editor.
6. Replace placeholders with local/remote images.
7. Save draft.

## Notes

- This skill intentionally does not include theme-system style switching.
- Styling should be produced by `aki-context-to-html` only.
- If `aki-context-to-html` cannot be found, set `AKI_CONTEXT_TO_HTML_DIR`.
