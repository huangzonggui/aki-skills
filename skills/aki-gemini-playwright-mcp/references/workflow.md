# Workflow

## Goal
Generate an image via Gemini web using Playwright automation, without paid API calls.

## Steps
1. Install deps in `scripts/`:
   - `bun install`
2. Run MCP server:
   - `bun scripts/mcp-server.ts`
3. Ensure Gemini login:
   - The first run opens a Chromium profile at `~/Library/Application Support/baoyu-skills/gemini-mcp/chrome-profile`.
   - Log in once and keep the tab on `https://gemini.google.com/app`.
4. Call the MCP tool:
   - `generateGeminiImage` with `prompt` and `outputPath`.

## Notes
- If the editor is not ready, the tool will wait and error with a login hint.
- For stable results, keep Chrome in the foreground when generating.
