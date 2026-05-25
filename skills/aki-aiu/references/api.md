# AI 中转站接口与字段说明（aki-aiu 用到）

## 已知平台

| Profile | Base URL | 风格 | 备注 |
|---|---|---|---|
| `dshub` | `https://api.dshub.top` | `new-api` | 对 new-api 端点已验证；quota 按 `500000 = $1` 换算 |
| `cygces` | `https://codex-manager.cygces.com` | `sub2api` | Token Wave / Sub2API 管理后台；Hermes/Codex key 在这里查；别名 `cyg`、`sub2api`、`token-wave` |

# new-api 接口与字段说明

适用于任何 [new-api](https://github.com/Calcium-Ion/new-api) 部署，已对 dshub.top 验证。

## 鉴权
- `POST /api/user/login` body: `{"username":"...","password":"..."}`，返回 `data.id` 即 user id，并下发 `session` cookie
- 后续请求需要带 cookie + header `New-Api-User: <user_id>`，缺一不可

## 端点
- `GET /api/user/self` —— 账户信息
  - `quota`：通用余额（quota）
  - `used_quota`：累计已用（quota）
  - `group`：所属分组
  - `request_count`：累计请求数
- `GET /api/subscription/self` —— 订阅套餐
  - `subscriptions[].subscription.amount_total / amount_used`：当前周期发放总量 / 已用
  - `subscriptions[].subscription.lifetime_amount_total / lifetime_amount_used`：套餐池累计总量 / 已用
  - `subscriptions[].subscription.end_time`：套餐到期 unix 秒
  - `subscriptions[].subscription.next_reset_time`：下次额度重置 unix 秒
  - `subscriptions[].plan.total_amount`：每周期发放上限
  - `subscriptions[].plan.title / subtitle`：套餐名
- `GET /api/usage/token` —— 当前 Bearer API Key 的额度信息
  - Header：`Authorization: Bearer <API_KEY>`
  - `total_granted`：API Key 总额度
  - `total_used`：API Key 已用额度
  - `total_available`：API Key 剩余额度
  - `unlimited_quota`：是否不限额度
  - `model_limits / model_limits_enabled`：模型限制
  - `expires_at`：API Key 到期 unix 秒，`0` 表示永不过期

## 单位换算
- `500000 quota = $1`（new-api 默认计费精度）
- aiu.py 用 `QUOTA_PER_USD = 500000` 统一换算，所有 `*_usd` 字段直接是美元

## Sub2API / cygces 后台

`https://codex-manager.cygces.com/keys` 不是标准 new-api 前端，当前使用 `/api/v1` 后台接口。

- `POST /api/v1/auth/login`
  - body: `{"email":"...","password":"..."}`
  - 返回 `access_token`
- `GET /api/v1/auth/me`
  - 当前用户信息
- `GET /api/v1/keys?page=1&page_size=100`
  - `items[].quota`：API Key 总额度（USD）
  - `items[].quota_used`：API Key 已用额度（USD）
  - `items[].status`：`active` / `inactive` / `quota_exhausted` / `expired`
  - `items[].expires_at`：到期时间，空值表示永不过期
  - `items[].rate_limit_5h / rate_limit_1d / rate_limit_7d`：周期限额（USD）
- `POST /api/v1/usage/dashboard/api-keys-usage`
  - body: `{"api_key_ids":[...]}`
  - 返回每个 key 的 `today_actual_cost` 和 `total_actual_cost`
