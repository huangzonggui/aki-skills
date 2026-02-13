---
name: aki-wechat-dajiala-fetcher
description: Run the bundled dajiala.com API-based WeChat official account fetcher to pull article lists/details/comments. Use when asked to抓取微信公众号文章/对标账号历史 via Dajiala API.
---

# Aki WeChat Dajiala Fetcher

Run the bundled `wechat_agent.py` to fetch WeChat official account history and article details.

## Setup

- Store the key outside git:
  - Put it in `${SKILL_DIR}/agent.json`, or
  - Export `DAJIALA_KEY`, or
  - Create `${SKILL_DIR}/.env` with `DAJIALA_KEY=...` (wrapper auto-loads).

## Quick Start

```bash
python3 ${SKILL_DIR}/scripts/run.py --url "https://mp.weixin.qq.com/s?__biz=..."
```

## Defaults

- Output directory defaults to `/Users/aki/Downloads/Browsers/自媒体` unless `--output` is provided.

## Notes

- Use `${SKILL_DIR}/scripts/run.py` to launch (keeps defaults and config in the skill).
- Pass through any `wechat_agent.py` args (e.g., `--biz`, `--name`, `--prompt`, `--max-pages`).
