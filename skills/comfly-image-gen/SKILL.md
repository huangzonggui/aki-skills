---
name: comfly-image-gen
description: Generate images via the Comfly proxy API (Nano Banana / Nano Banana HD) from image_prompts.md and save outputs. Use when asked to run Comfly/Nano Banana image generation.
---

# Comfly Image Generation

Use the bundled script to call the Comfly proxy API and generate images from `image_prompts.md`.

## Requirements

- A topic folder path (contains `outputs/image_prompts.md`).
- A config path for `workflow.config.json` (or set env vars).
- API key must stay private (use env var or config, never print it).

## Key safety

- Do NOT hardcode or echo the API key in logs.
- Prefer `COMFLY_API_KEY` in the environment.
- If the key is stored in `workflow.config.json`, do not commit it.

## Configuration

Add `image_api` to `workflow.config.json`:

```json
{
  "image_api": {
    "base_url": "https://<comfly-proxy-host>",
    "path": "/v1/images/generations",
    "api_key": "",
    "image_model": "nano-banana",
    "response_format": "url",
    "aspect_ratio": "4:5"
  }
}
```

Model options:
- `nano-banana` (default)
- `nano-banana-hd` (4K / pro)

Env overrides:
- `COMFLY_API_KEY`
- `COMFLY_API_BASE_URL`
- `COMFLY_IMAGE_MODEL`

Optional local secrets (not committed):
- Create `skills/comfly-image-gen/.env` and put `COMFLY_API_KEY=...`
- The script will auto-load this file at runtime.

## Usage

⚠️ **IMPORTANT**: Always run WITHOUT `--confirm` first to preview what will be generated!

**Step 1 - Preview (DRY-RUN, NO COST):**
```bash
python3 /path/to/skills/comfly-image-gen/scripts/comfly_image_gen.py \
  --topic /path/to/topic \
  --config /path/to/workflow.config.json
```
Check the output - verify the number of images and prompt content are correct.

**Step 2 - Generate (PAID API CALL):**
```bash
python3 /path/to/skills/comfly-image-gen/scripts/comfly_image_gen.py \
  --topic /path/to/topic \
  --config /path/to/workflow.config.json \
  --confirm
```

Notes:
- Outputs saved to `<topic>/outputs/images/`.
- Metadata saved to `<topic>/outputs/image_generations.json`.
- Use `--force` only if you want to overwrite existing outputs.

## References

- `references/nano-banana.md`
- `references/comfly-api-doc.md`
