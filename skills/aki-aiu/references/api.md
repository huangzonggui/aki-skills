# new-api 接口与字段说明（aki-aiu 用到）

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

## 单位换算
- `500000 quota = $1`（new-api 默认计费精度）
- aiu.py 用 `QUOTA_PER_USD = 500000` 统一换算，所有 `*_usd` 字段直接是美元
