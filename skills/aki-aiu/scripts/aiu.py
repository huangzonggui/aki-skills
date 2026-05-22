#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dshub_monitor.py
----------------
定时轮询 https://api.dshub.top 中转站，输出：
  - 通用额度（账户余额）
  - 订阅套餐总额度 / 已用 / 剩余
  - 今日发放额度 / 今日已用 / 今日剩余
  - 套餐到期时间 / 当日清零结算时间 / 距到期/重置 倒计时

仅依赖 Python 标准库（urllib + json）。
凭据从同目录 .env 读取，不写入代码。

用法：
  python3 dshub_monitor.py              # 持续刷新（默认间隔 30s，按 Ctrl+C 退出）
  python3 dshub_monitor.py --once       # 跑一次就退出
  python3 dshub_monitor.py --json       # 输出 JSON（适合喂给其他工具/脚本）
  python3 dshub_monitor.py --interval 10
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

# new-api 的额度单位：500000 quota = 1 USD
QUOTA_PER_USD = 500_000


# ---------- .env loader ----------
def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


# ---------- HTTP client ----------
class DshubClient:
    def __init__(self, base: str, username: str, password: str):
        self.base = base.rstrip("/")
        self.username = username
        self.password = password
        self.user_id: int | None = None
        self.cookie_jar = CookieJar()
        self.opener = urlrequest.build_opener(
            urlrequest.HTTPCookieProcessor(self.cookie_jar)
        )
        self.opener.addheaders = [
            ("User-Agent", "Mozilla/5.0 (dshub-monitor)"),
            ("Accept", "application/json, text/plain, */*"),
        ]

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.base}{path}"
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.user_id is not None:
            headers["New-Api-User"] = str(self.user_id)
        req = urlrequest.Request(url, data=data, method=method, headers=headers)
        with self.opener.open(req, timeout=20) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
        try:
            return json.loads(payload)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"非 JSON 响应：{payload[:200]}") from e

    def login(self) -> None:
        data = self._request(
            "POST",
            "/api/user/login",
            {"username": self.username, "password": self.password},
        )
        if not data.get("success"):
            raise RuntimeError(f"登录失败：{data.get('message')}")
        self.user_id = int(data["data"]["id"])

    def fetch_self(self) -> dict:
        data = self._request("GET", "/api/user/self")
        if not data.get("success"):
            raise RuntimeError(f"获取账户信息失败：{data.get('message')}")
        return data["data"]

    def fetch_subscription(self) -> dict:
        data = self._request("GET", "/api/subscription/self")
        if not data.get("success"):
            raise RuntimeError(f"获取套餐信息失败：{data.get('message')}")
        return data["data"]


# ---------- formatting helpers ----------
def usd(quota: int | float) -> float:
    return round(float(quota) / QUOTA_PER_USD, 2)


def fmt_usd(quota: int | float) -> str:
    return f"${usd(quota):,.2f}"


def fmt_ts(ts: int | None) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def fmt_duration(seconds: int) -> str:
    if seconds <= 0:
        return "已到期"
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d}天")
    if h or d:
        parts.append(f"{h}小时")
    parts.append(f"{m}分钟")
    return "".join(parts)


# ---------- summary builder ----------
def build_summary(self_info: dict, sub_info: dict) -> dict:
    now = int(time.time())
    general_quota = int(self_info.get("quota", 0))
    used_quota_lifetime = int(self_info.get("used_quota", 0))

    subs = sub_info.get("subscriptions") or sub_info.get("all_subscriptions") or []
    sub_blocks: list[dict] = []
    for item in subs:
        sub = item.get("subscription", {})
        plan = item.get("plan", {})

        amount_total = int(sub.get("amount_total", 0))     # 当期周期总池
        amount_used = int(sub.get("amount_used", 0))       # 当期周期已用
        amount_remaining = max(amount_total - amount_used, 0)

        lifetime_total = int(sub.get("lifetime_amount_total", 0))
        lifetime_used = int(sub.get("lifetime_amount_used", 0))
        lifetime_remaining = max(lifetime_total - lifetime_used, 0)

        # 日卡场景：plan.total_amount = 每日发放额度
        daily_grant = int(plan.get("total_amount", 0))
        daily_used = amount_used   # 当日发放额度内的已用
        daily_remaining = max(daily_grant - daily_used, 0)

        end_time = int(sub.get("end_time", 0))
        next_reset = int(sub.get("next_reset_time", 0))

        sub_blocks.append({
            "plan_title": plan.get("title", ""),
            "plan_subtitle": plan.get("subtitle", ""),
            "group": sub.get("upgrade_group", ""),
            "status": sub.get("status", ""),
            "stacking_mode": sub.get("stacking_mode", ""),
            "reset_period": plan.get("quota_reset_period", ""),
            "today": {
                "grant_quota": daily_grant,
                "used_quota": daily_used,
                "remaining_quota": daily_remaining,
                "grant_usd": usd(daily_grant),
                "used_usd": usd(daily_used),
                "remaining_usd": usd(daily_remaining),
            },
            "pool": {
                "total_quota": lifetime_total,
                "used_quota": lifetime_used,
                "remaining_quota": lifetime_remaining,
                "total_usd": usd(lifetime_total),
                "used_usd": usd(lifetime_used),
                "remaining_usd": usd(lifetime_remaining),
            },
            "expire_at": end_time,
            "expire_at_text": fmt_ts(end_time),
            "expire_in_seconds": max(end_time - now, 0),
            "next_reset_at": next_reset,
            "next_reset_at_text": fmt_ts(next_reset),
            "next_reset_in_seconds": max(next_reset - now, 0),
        })

    return {
        "fetched_at": now,
        "fetched_at_text": fmt_ts(now),
        "user": {
            "username": self_info.get("username"),
            "display_name": self_info.get("display_name"),
            "group": self_info.get("group"),
            "request_count": self_info.get("request_count"),
        },
        "general": {
            "quota": general_quota,
            "usd": usd(general_quota),
            "used_quota_lifetime": used_quota_lifetime,
            "used_usd_lifetime": usd(used_quota_lifetime),
        },
        "subscriptions": sub_blocks,
    }


# ---------- rendering ----------
ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "cyan": "\033[36m",
    "red": "\033[31m",
    "magenta": "\033[35m",
    "clear": "\033[2J\033[H",
}


def _bar(used: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return "[" + "·" * width + "]"
    ratio = min(max(used / total, 0), 1)
    filled = int(width * ratio)
    color = ANSI["green"]
    if ratio >= 0.9:
        color = ANSI["red"]
    elif ratio >= 0.7:
        color = ANSI["yellow"]
    return f"[{color}{'█' * filled}{ANSI['reset']}{'·' * (width - filled)}] {ratio*100:5.1f}%"


def render_text(summary: dict, color: bool = True) -> str:
    def c(key: str) -> str:
        return ANSI[key] if color else ""

    lines: list[str] = []
    user = summary["user"]
    g = summary["general"]
    lines.append(
        f"{c('bold')}🌊 Token Wave 监控  ·  {summary['fetched_at_text']}{c('reset')}"
    )
    lines.append(
        f"  用户：{c('cyan')}{user['display_name']}{c('reset')}（{user['username']}）"
        f"  分组：{user['group']}  累计请求：{user['request_count']}"
    )
    lines.append(
        f"  通用额度：{c('bold')}${g['usd']:.2f}{c('reset')}"
        f"   历史消耗：${g['used_usd_lifetime']:.2f}"
    )

    if not summary["subscriptions"]:
        lines.append(f"  {c('dim')}（无生效套餐）{c('reset')}")
        return "\n".join(lines)

    for i, sub in enumerate(summary["subscriptions"], 1):
        lines.append("")
        lines.append(
            f"{c('magenta')}■ 套餐 #{i}  {sub['plan_title']}{c('reset')}"
            f"  {c('dim')}{sub['plan_subtitle']}{c('reset')}"
        )
        lines.append(f"  分组：{sub['group']}   状态：{sub['status']}   叠加：{sub['stacking_mode']}")

        today = sub["today"]
        lines.append(
            f"  {c('bold')}今日{c('reset')}  发放 ${today['grant_usd']:.2f}"
            f"   已用 {c('yellow')}${today['used_usd']:.2f}{c('reset')}"
            f"   剩余 {c('green')}${today['remaining_usd']:.2f}{c('reset')}"
        )
        lines.append(
            "         " + _bar(today["used_quota"], today["grant_quota"]) if color
            else "         " + _bar(today["used_quota"], today["grant_quota"], 24)
        )

        pool = sub["pool"]
        lines.append(
            f"  套餐池  总 ${pool['total_usd']:.2f}"
            f"   已用 ${pool['used_usd']:.2f}"
            f"   剩余 {c('green')}${pool['remaining_usd']:.2f}{c('reset')}"
        )
        lines.append("         " + _bar(pool["used_quota"], pool["total_quota"]))

        lines.append(
            f"  当日清零：{sub['next_reset_at_text']}  "
            f"（{c('dim')}{fmt_duration(sub['next_reset_in_seconds'])}后{c('reset')}）"
        )
        lines.append(
            f"  套餐到期：{sub['expire_at_text']}  "
            f"（{c('dim')}{fmt_duration(sub['expire_in_seconds'])}后{c('reset')}）"
        )
    return "\n".join(lines)


# ---------- main loop ----------
def run_once(client: DshubClient) -> dict:
    if client.user_id is None:
        client.login()
    try:
        self_info = client.fetch_self()
        sub_info = client.fetch_subscription()
    except HTTPError as e:
        if e.code in (401, 403):
            client.login()
            self_info = client.fetch_self()
            sub_info = client.fetch_subscription()
        else:
            raise
    return build_summary(self_info, sub_info)


def main() -> int:
    parser = argparse.ArgumentParser(description="dshub.top 余额/套餐定时监控")
    parser.add_argument("--once", action="store_true", help="只执行一次后退出")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而非可读文本")
    parser.add_argument("--interval", type=int, default=None, help="刷新间隔（秒）")
    parser.add_argument("--no-color", action="store_true", help="禁用 ANSI 颜色")
    parser.add_argument("--no-clear", action="store_true", help="不清屏，每次追加输出")
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    # .env 加载优先级：$AIU_ENV_FILE > $SKILL_DIR/../.env > $SKILL_DIR/.env > ~/.config/aiu/.env
    candidates = []
    if os.environ.get("AIU_ENV_FILE"):
        candidates.append(Path(os.environ["AIU_ENV_FILE"]))
    candidates += [here.parent / ".env", here / ".env", Path.home() / ".config" / "aiu" / ".env"]
    for c in candidates:
        if c.exists():
            load_env(c)
            break

    base = os.environ.get("DSHUB_BASE", "https://api.dshub.top")
    username = os.environ.get("DSHUB_USERNAME", "")
    password = os.environ.get("DSHUB_PASSWORD", "")
    interval = args.interval if args.interval is not None else int(
        os.environ.get("DSHUB_INTERVAL", "30") or 30
    )
    if not username or not password:
        print("错误：请在 .env 中设置 DSHUB_USERNAME / DSHUB_PASSWORD", file=sys.stderr)
        return 2

    client = DshubClient(base, username, password)

    def emit(summary: dict) -> None:
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            if not args.once and not args.no_clear:
                sys.stdout.write(ANSI["clear"])
            print(render_text(summary, color=not args.no_color))
            sys.stdout.flush()

    if args.once:
        emit(run_once(client))
        return 0

    print(f"开始监控 {base} ，每 {interval}s 刷新一次（Ctrl+C 退出）", file=sys.stderr)
    try:
        while True:
            try:
                emit(run_once(client))
            except (HTTPError, URLError, RuntimeError) as e:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{ts}] 刷新失败：{e}", file=sys.stderr)
                client.user_id = None  # 强制下次重新登录
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n已停止。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
