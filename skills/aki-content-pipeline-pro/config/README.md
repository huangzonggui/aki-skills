# Configuration Guide

All API keys and model settings are loaded in this order (first match wins):

1. System environment variables
2. `~/.config/ai/keys.env`
3. `~/.config/comfly/config` (legacy, Comfly keys only)
4. Built-in defaults

## Required Config

| Key | Purpose | Where to get it |
|-----|---------|-----------------|
| `COMFLY_API_KEY` | Image generation API | https://ai.comfly.chat |
| `COMFLY_IMAGE_MODEL` | Image model name | gpt-image-2 / gemini-2.5-flash-image |

## Optional Config

| Key | Purpose | Notes |
|-----|---------|-------|
| `OPENROUTER_API_KEY` | Fallback image provider | https://openrouter.ai |
| `COMFLY_CHAT_MODEL` | LLM for content planning | Defaults to gemini-3-pro-preview-thinking |
| `WECHAT_APP_ID` | WeChat publish | Full pipeline only |
| `WECHAT_APP_SECRET` | WeChat publish | Full pipeline only |

## Platform-Specific Paths

These are auto-detected, only set if the default is wrong:

| Env Var | Purpose | macOS default | Windows default |
|---------|---------|---------------|-----------------|
| `JY_PROJECTS_ROOT` | Jianying project directory | `~/Movies/JianyingPro/...` | `%USERPROFILE%\...` |
| `AKI_SKILLS_REPO_ROOT` | Skill repo root | Auto-detected | Auto-detected |
