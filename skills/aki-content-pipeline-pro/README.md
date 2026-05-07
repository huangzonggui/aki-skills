# Aki Content Pipeline Pro

AI-powered one-to-many content creation pipeline. ¥499.

## What It Does

Input reference links + your opinions → AI generates draft → human review → renders hand-drawn style images → multi-platform copies → video scripts → jianying drafts → WeChat publish.

## Quick Start

1. Clone/download this repository
2. Set up API keys: `cp config/keys.env.example ~/.config/ai/keys.env` (edit it with your keys)
3. Run check: `python scripts/check_env.py`
4. Start: `python scripts/pipeline.py --intent init_topic --cwd . --title "Your Topic" --mode test`

## Requirements

- Python 3.10+ (zero pip dependencies for core pipeline)
- Comfly API key (for image generation)
- Optional: `pip install Pillow` (cross-platform images)
- Optional: ffmpeg (video export), Jianying Pro (video drafts)

## What You Get (¥499 all-inclusive)

| Capability | Tech needed |
|-----------|-------------|
| Methodology + Knowledge Base | Read & ask questions |
| AI Draft Generation | Python 3 + Comfly API |
| Hand-drawn Image Render | Python 3 + Comfly API |
| Multi-platform Copies | Python 3 |
| Video Scripts + Drafts | + ffmpeg + Jianying |
| WeChat Publish | + WeChat AppID/Secret |

## Works With

Claude Code · OpenClaw · QClaw (Tencent) · Codex

## Docs

- AGENTS.md — AI agent guidance
- SETUP.md — Step-by-step installation
- SKILL.md — Complete workflow specification
- config/README.md — Configuration reference
