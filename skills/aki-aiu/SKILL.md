---
name: aki-aiu
description: Check AI relay station (new-api compatible, e.g. dshub.top / Token Wave) account balance, daily quota, subscription pool, and expiration. Use when user asks about AI usage, remaining quota, today's allowance, plan expiration, or wants a recurring monitor of their relay station credits. Login with username/password and parse subscription state.
---

# aki-aiu — AI 用量查询

查询任意 [new-api](https://github.com/Calcium-Ion/new-api) 兼容的 AI 中转站（如 dshub.top / Token Wave）的额度与套餐用量。返回当前通用余额、今日发放/已用/剩余、套餐池总量、套餐到期、当日清零时间等。可单次查询，也可常驻定时刷新。

## 已知中转站信息

| Profile | 平台/后台 | Base URL | API 风格 | 说明 |
|---|---|---|---|---|
| `dshub` | TokenWave / dshub.top | `https://api.dshub.top` | `new-api` | `custom:tokenwave` 对应中转站；`500000 quota = $1`；支持账号套餐与 Bearer API Key 用量查询；别名：`tokenwave`、`token-wave` |
| `cygces` | cygces / Sub2API | `https://codex-manager.cygces.com` | `sub2api` | `custom:cygces` 对应中转站；Hermes/Codex 相关 API Key 管理后台；别名：`cyg`、`codex`、`sub2api` |

Aki 的凭据集中放在 AI keys 文件，不进仓库：MacBook 默认 `/Users/aki/.config/ai/keys.env`；Hermes/Linux 环境回退 `~/.config/ai/keys.env`；临时覆盖用 `AIU_ENV_FILE=/path/to/keys.env`；默认集中路径覆盖用 `AIU_KEYS_ENV=/path/to/keys.env`。

## When to use

- 用户问"还剩多少额度 / 今天还能用多少 / 套餐什么时候到期"
- 用户想盯着用量看，要求每隔几分钟刷新一次
- 用户要把额度数据喂给其它脚本（告警、统计、看板）

## Quick start

```bash
# 1. 配置凭据（首次，把示例复制到集中 keys.env 后填真实值）
# MacBook：/Users/aki/.config/ai/keys.env
# Hermes/Linux：~/.config/ai/keys.env
mkdir -p ~/.config/ai
cp ${SKILL_DIR}/.env.example ~/.config/ai/keys.env
chmod 600 ~/.config/ai/keys.env

# keys.env 示例字段：
DSHUB_BASE=https://api.dshub.top
DSHUB_API_STYLE=new-api
DSHUB_USERNAME=<你的账号>
DSHUB_PASSWORD=***

# cygces / Token Wave / Hermes API Key 查询（Sub2API 后台）
CYGCES_BASE=https://codex-manager.cygces.com
CYGCES_API_STYLE=sub2api
CYGCES_USERNAME=<你的账号>
CYGCES_PASSWORD=***
CYGCES_HERMES_API_KEY=***

# 2. 单次查询（人类可读；不传 profile 默认查两个中转站）
python3 ${SKILL_DIR}/scripts/aiu.py --once
python3 ${SKILL_DIR}/scripts/aiu.py --profile both --once
python3 ${SKILL_DIR}/scripts/aiu.py --profile cygces --once

# 3. 单次查询（JSON，喂给其它脚本；默认返回 {"profiles": [...]}）
python3 ${SKILL_DIR}/scripts/aiu.py --once --json
python3 ${SKILL_DIR}/scripts/aiu.py both --once --json
python3 ${SKILL_DIR}/scripts/aiu.py --profile cygces --once --json

# 4. 定时刷新面板（默认 30s）
python3 ${SKILL_DIR}/scripts/aiu.py
python3 ${SKILL_DIR}/scripts/aiu.py --interval 60     # 1 分钟
python3 ${SKILL_DIR}/scripts/aiu.py --interval 300    # 5 分钟
```

凭据默认从集中 keys 文件读取：MacBook `/Users/aki/.config/ai/keys.env`，Hermes/Linux `~/.config/ai/keys.env`。如需临时指定其它文件，可设置 `$AIU_ENV_FILE`；如需修改默认集中路径，可设置 `$AIU_KEYS_ENV`。`.env.example` 只放占位字段，不放真实密钥。

## Options

| Parameter | Description | Default |
|---|---|---|
| `--profile <name>` | 配置 profile；支持 `dshub` / `cygces` / `all` / `both`，也可逗号或 `+` 分隔（如 `dshub,cyg`） | 默认查 `dshub` + `cygces` |
| `--once` | 跑一次后退出 | false |
| `--json` | 输出 JSON | false |
| `--interval <sec>` | 刷新间隔（秒） | 30 |
| `--no-color` | 关闭 ANSI 颜色 | false |
| `--no-clear` | 不清屏，每次追加输出 | false |

## Output (JSON shape)

调 `--once --json` 得到：

```json
{
  "fetched_at": 1779370901,
  "source": { "profile": "cygces", "base": "https://codex-manager.cygces.com" },
  "user": { "username": "...", "group": "...", "request_count": 2643 },
  "general": { "usd": 7.11, "used_usd_lifetime": 420.54 },
  "token_usage": {
    "name": "Hermes",
    "total_granted_usd": 5.0,
    "total_used_usd": 2.0,
    "total_available_usd": 3.0,
    "unlimited_quota": false,
    "expires_at_text": "永不过期"
  },
  "subscriptions": [
    {
      "plan_title": "日卡 100$/日",
      "today":  { "grant_usd": 100.0, "used_usd": 55.0, "remaining_usd": 45.0 },
      "pool":   { "total_usd": 700.0, "used_usd": 407.0, "remaining_usd": 293.0 },
      "expire_at_text": "2026-05-22 00:00:00",
      "expire_in_seconds": 8391,
      "next_reset_at_text": "2026-05-22 00:00:00",
      "next_reset_in_seconds": 8391
    }
  ]
}
```

new-api 内部 quota 单位换算：`500000 quota = $1`，脚本已统一换算成 USD。

## How it works

new-api profile：

1. POST `/api/user/login` → 拿 cookie + user id
2. GET  `/api/user/self`           → 通用额度、累计消耗
3. GET  `/api/subscription/self`   → 套餐池、今日发放/已用、到期时间
4. GET  `/api/usage/token`         → API Key 本身额度、已用、剩余、到期
5. session 失效自动重登

cygces/Sub2API profile：

1. POST `/api/v1/auth/login` → 拿 access token
2. GET  `/api/v1/auth/me`
3. GET  `/api/v1/keys`
4. POST `/api/v1/usage/dashboard/api-keys-usage` → 今日和累计消耗

## Recurring monitor (定时器)

在终端常驻一份：

```bash
python3 ${SKILL_DIR}/scripts/aiu.py --interval 300       # 每 5 分钟刷新
python3 ${SKILL_DIR}/scripts/aiu.py --no-color --no-clear --interval 300 >> ~/aiu.log 2>&1 &
```

或交给 launchd / cron 周期跑 `--once --json` 喂给告警脚本。

## Reference

- API 字段说明 → `references/api.md`
- 单文件无依赖：Python 3.8+ 标准库（urllib + json），不需要 pip。
