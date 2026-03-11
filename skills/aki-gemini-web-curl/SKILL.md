---
name: aki-gemini-web-curl
description: Generate images through Gemini Web with existing Chrome login cookies, without opening a browser window. Use this whenever the user wants Gemini web image generation, batch prompt-file generation, stricter ratio retries, or wants to avoid the old Playwright MCP flow. Prefer this skill over aki-gemini-playwright-mcp for no-window generation, cookie reuse, raw-response capture, and resolution validation.
---

# Aki Gemini Web Curl

Use Gemini Web through the logged-in Chrome cookie jar and `curl --http1.1`.

This skill is the replacement path when:
- the old Playwright skill is unstable
- the user wants to reuse the current Google login state
- the user wants prompt-file driven batch generation
- the user wants ratio retry and output validation
- the user wants raw Gemini response files kept for debugging

## What This Skill Takes

Primary inputs:
- `prompt` or `prompt file`
- `output path`

Optional inputs:
- `chat model`: `gemini-2.5-pro` / `gemini-3-pro` / `gemini-2.5-flash`
- `target ratio`: default `3:4`
- `reroll count`: how many times to retry until ratio passes
- `proxy`: optional override such as `socks5://127.0.0.1:7890`
- `raw output path`
- `metadata output path`

## What This Skill Outputs

For each generated image:
- saved image file
- raw Gemini web response `.txt`
- metadata `.json`

The metadata includes:
- selected chat model header
- detected backend hint such as `Nano Banana 2`
- original candidate dimensions parsed from Gemini raw response
- downloaded file dimensions
- whether ratio validation passed

## Default Behavior

1. Read Google cookies from the local Chrome profile.
2. Open `https://gemini.google.com/app` through `curl --http1.1`.
3. Extract the Gemini access token.
4. Submit the prompt to the Gemini Web `StreamGenerate` endpoint.
5. Parse raw response for generated image candidates and expected dimensions.
6. Download candidates with a cookie jar.
7. Validate ratio and dimensions.
8. Retry if the result does not meet the target ratio.

## Important Limits

- This skill does not open a browser window.
- It reuses existing Chrome login cookies.
- Google may still route image generation to `Nano Banana 2` even if the chat model header is Pro.
- If the user explicitly needs Nano Banana Pro from the Gemini app UI, that is a separate browser workflow.

## Commands

Single prompt file:

```bash
python3 /Users/aki/Development/code/aki-skills/skills/aki-gemini-web-curl/scripts/gemini_web_curl.py \
  --prompt-file /absolute/path/to/prompt.md \
  --output /absolute/path/to/output.png
```

Inline prompt:

```bash
python3 /Users/aki/Development/code/aki-skills/skills/aki-gemini-web-curl/scripts/gemini_web_curl.py \
  --prompt "生成一张竖版 3:4 高信息密度手绘图" \
  --output /absolute/path/to/output.png
```

Batch prompt files:

```bash
python3 /Users/aki/Development/code/aki-skills/skills/aki-gemini-web-curl/scripts/batch_generate.py \
  --items /absolute/path/to/items.json
```

`items.json` shape:

```json
[
  {
    "prompt_file": "/abs/cover_prompt.md",
    "output": "/abs/cover.png"
  },
  {
    "prompt_file": "/abs/series_01_prompt.md",
    "output": "/abs/series_01.png"
  }
]
```

## Troubleshooting

If Gemini Web is flaky:
- read `references/troubleshooting.md`
- prefer TUN mode over mixed `HTTP_PROXY` / `HTTPS_PROXY`
- if using a proxy override, pass only one `ALL_PROXY`-style endpoint

