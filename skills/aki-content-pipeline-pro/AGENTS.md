# AGENTS.md — Agent Guidance for aki-content-pipeline-pro

## What This Is

AI-powered content creation pipeline. Input reference links + personal opinions → AI generates draft → human review → generates hand-drawn style images → multi-platform copies → video scripts → jianying drafts → WeChat publish.

## Entry Points (for any agent)

1. **Direct execution**: `python scripts/pipeline.py --intent <intent> --topic-root <path>`
2. **Chat mode**: Agent reads SKILL.md and invokes pipeline.py as instructed
3. **Chat orchestrator** (Claude Code only): `python scripts/chat_orchestrator.py`

## Agent Compatibility

| Agent | SKILL.md | Python Scripts | Notes |
|-------|----------|---------------|-------|
| Claude Code | Native | Direct call | chat_orchestrator.py available |
| OpenClaw | Native | Direct call | Same SKILL.md format |
| QClaw (Tencent) | Native | Use pipeline.bat | Windows batch wrapper |
| Codex | Native | agents/openai.yaml | Interface spec ready |

## Required Environment

- Python 3.10+
- `COMFLY_API_KEY` in `~/.config/ai/keys.env` (for image generation)
- Optional: `pip install Pillow` (cross-platform image processing)
- Optional: ffmpeg (video export only)

## Available Intents

`init_topic`, `ingest_sources`, `summarize_core_note`, `co_create_core_note`, `approve_core_note`, `derive_platform_copies`, `generate_prompts`, `render_images`, `derive_video_scripts`, `approve_video_scripts`, `build_video_package`, `publish_wechat_drafts`, `resume`, `rework`

## Key Constraints (always enforce)

1. Do not copy images between platform directories (wechat/xiaohongshu/douyin)
2. Core note approval (SHA-256) must precede platform derivation
3. Prompt approval must precede image rendering
4. Video script approval must precede video package build
5. Never fabricate information — mark uncertain content as "存疑待核实"
