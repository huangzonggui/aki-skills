---
name: comfly-image-gen
description: Generate images via the Comfly proxy API from image_prompts.md and save outputs. Uses unified config at ~/.config/comfly/config.
---

# Comfly Image Generation

Use the bundled script to call the Comfly proxy API and generate images from `image_prompts.md`.

## Requirements

- A topic folder path (contains `outputs/image_prompts.md`).
- Unified config file: `~/.config/comfly/config`.

## Key safety

- Do NOT hardcode or echo the API key in logs.
- If keys are stored in `~/.config/comfly/config`, do not commit or share it.

## Configuration

`~/.config/comfly/config` is the source of truth for all skills.

Write it like this:

```bash
COMFLY_API_KEY=...
COMFLY_API_BASE_URL=https://ai.comfly.chat
COMFLY_IMAGE_MODEL=gemini-3.1-flash-image-preview
```

Quick bootstrap on a new machine:

```bash
mkdir -p ~/.config/comfly
cat > ~/.config/comfly/config <<'EOF'
COMFLY_API_KEY=your-api-key
COMFLY_API_BASE_URL=https://ai.comfly.chat
COMFLY_IMAGE_MODEL=gemini-3.1-flash-image-preview
EOF
```

Read logic (important):
- Script reads `~/.config/comfly/config` by default.
- 当前默认只把 `~/.config/comfly/config` 当成 Comfly 凭证与模型配置来源。
- `--model` is intentionally unsupported.
- `--config` is optional JSON override for request body fields (size/n/response format etc.).

## Usage

Dry-run (no paid call):

```bash
python3 /path/to/skills/comfly-image-gen/scripts/comfly_image_gen.py \
  --topic /path/to/topic
```

Generate images (paid call):

```bash
python3 /path/to/skills/comfly-image-gen/scripts/comfly_image_gen.py \
  --topic /path/to/topic \
  --confirm
```

Notes:
- Outputs saved to `<topic>/outputs/images/`.
- Metadata saved to `<topic>/outputs/image_generations.json`.
- Use `--force` only if you want to overwrite existing outputs.

## References

- `references/nano-banana.md`
- `references/comfly-api-doc.md`
