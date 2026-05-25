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
DEFAULT_QUERY_PROFILES = ("dshub", "cygces")
MULTI_PROFILE_ALIASES = {"all", "both"}
PROFILE_ALIASES = {
    "tokenwave": "dshub",
    "token-wave": "dshub",
    "cyg": "cygces",
    "codex": "cygces",
    "sub2api": "cygces",
}
DEFAULT_BASES = {
    "dshub": "https://api.dshub.top",
    "cygces": "https://codex-manager.cygces.com",
}
DEFAULT_API_STYLES = {
    "dshub": "new-api",
    "cygces": "sub2api",
}
# Aki 的集中 API keys 文件。MacBook 上固定使用 /Users/aki/.config/ai/keys.env；
# Hermes/Linux 环境没有 /Users/aki 时，回退到当前用户 ~/.config/ai/keys.env。
# 可用 AIU_ENV_FILE 指向一次性文件，或 AIU_KEYS_ENV 覆盖默认集中配置文件路径。
AI_KEYS_ENV = Path(os.environ.get("AIU_KEYS_ENV", "/Users/aki/.config/ai/keys.env"))
FALLBACK_AI_KEYS_ENV = Path.home() / ".config" / "ai" / "keys.env"
KNOWN_PROFILES = {
    "dshub": {
        "base": DEFAULT_BASES["dshub"],
        "api_style": "new-api",
        "auth": "用户名/密码登录；可选 DSHUB_API_KEY 查询 Bearer API Key 额度",
        "quota_unit": "500000 quota = $1",
        "runtime_provider": "custom:tokenwave / https://api.dshub.top/v1",
    },
    "cygces": {
        "base": DEFAULT_BASES["cygces"],
        "api_style": "sub2api",
        "auth": "CYGCES_USERNAME / CYGCES_PASSWORD 登录 Sub2API 后台；CYGCES_HERMES_API_KEY 记录 Hermes 使用的 API Key",
        "runtime_provider": "custom:cygces / https://codex.cygces.com/v1",
        "key_page": "https://codex-manager.cygces.com/keys",
    },
}


class AiuConfig:
    def __init__(
        self,
        profile: str,
        base: str,
        username: str,
        password: str,
        api_key: str,
        interval: int,
        api_style: str = "new-api",
    ):
        self.profile = profile
        self.base = base
        self.username = username
        self.password = password
        self.api_key = api_key
        self.interval = interval
        self.api_style = api_style


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
    def __init__(self, base: str, username: str = "", password: str = "", api_key: str = ""):
        self.base = base.rstrip("/")
        self.username = username
        self.password = password
        self.api_key = api_key
        self.user_id: int | None = None
        self.cookie_jar = CookieJar()
        self.opener = urlrequest.build_opener(
            urlrequest.HTTPCookieProcessor(self.cookie_jar)
        )
        self.opener.addheaders = [
            ("User-Agent", "Mozilla/5.0 (dshub-monitor)"),
            ("Accept", "application/json, text/plain, */*"),
        ]

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        bearer: str | None = None,
    ) -> dict:
        url = f"{self.base}{path}"
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
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

    def fetch_token_usage(self) -> dict:
        if not self.api_key:
            return {}
        data = self._request("GET", "/api/usage/token", bearer=self.api_key)
        if not (data.get("success") or data.get("code") is True):
            raise RuntimeError(f"获取 API Key 额度失败：{data.get('message')}")
        return data["data"]


class Sub2apiClient:
    def __init__(self, base: str, username: str, password: str):
        self.base = base.rstrip("/")
        self.api_base = f"{self.base}/api/v1"
        self.username = username
        self.password = password
        self.access_token = ""
        self.refresh_token = ""
        self.opener = urlrequest.build_opener()
        self.opener.addheaders = [
            ("User-Agent", "Mozilla/5.0 (aiu-monitor)"),
            ("Accept", "application/json, text/plain, */*"),
        ]

    def _unwrap(self, payload: dict) -> Any:
        if "code" in payload:
            if payload.get("code") == 0:
                return payload.get("data")
            raise RuntimeError(f"请求失败：{payload.get('message') or payload.get('detail')}")
        if payload.get("success") is False:
            raise RuntimeError(f"请求失败：{payload.get('message') or payload.get('detail')}")
        return payload.get("data", payload)

    def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        url = f"{self.api_base}{path}"
        data = None
        headers = {"Content-Type": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        req = urlrequest.Request(url, data=data, method=method, headers=headers)
        with self.opener.open(req, timeout=20) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"非 JSON 响应：{payload[:200]}") from e
        return self._unwrap(parsed)

    def login(self) -> None:
        data = self._request(
            "POST",
            "/auth/login",
            {"email": self.username, "password": self.password},
        )
        if data.get("requires_2fa"):
            raise RuntimeError("登录需要 2FA，AIu 暂未支持自动输入 2FA")
        self.access_token = str(data.get("access_token") or "")
        self.refresh_token = str(data.get("refresh_token") or "")
        if not self.access_token:
            raise RuntimeError("登录失败：未返回 access_token")

    def fetch_me(self) -> dict:
        return self._request("GET", "/auth/me")

    def fetch_keys(self) -> dict:
        return self._request("GET", "/keys?page=1&page_size=100")

    def fetch_key_usage(self, ids: list[int]) -> dict:
        if not ids:
            return {}
        return self._request("POST", "/usage/dashboard/api-keys-usage", {"api_key_ids": ids})


# ---------- formatting helpers ----------
def usd(quota: int | float) -> float:
    return round(float(quota) / QUOTA_PER_USD, 2)


def fmt_usd(quota: int | float) -> str:
    return f"${usd(quota):,.2f}"


def fmt_ts(ts: int | None) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def fmt_ts_from_any(value: Any) -> str:
    if not value:
        return "永不过期"
    if isinstance(value, (int, float)):
        return fmt_ts(int(value))
    text = str(value)
    try:
        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return text


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
def build_token_usage_summary(token_usage: dict) -> dict:
    total_granted = int(token_usage.get("total_granted", 0) or 0)
    total_used = int(token_usage.get("total_used", 0) or 0)
    total_available = int(token_usage.get("total_available", 0) or 0)
    model_limits = token_usage.get("model_limits") or {}
    if isinstance(model_limits, dict):
        models = sorted(k for k, enabled in model_limits.items() if enabled)
    else:
        models = []
    expires_at = int(token_usage.get("expires_at", 0) or 0)
    return {
        "name": token_usage.get("name", ""),
        "total_granted_quota": total_granted,
        "total_used_quota": total_used,
        "total_available_quota": total_available,
        "total_granted_usd": usd(total_granted),
        "total_used_usd": usd(total_used),
        "total_available_usd": usd(total_available),
        "unlimited_quota": bool(token_usage.get("unlimited_quota")),
        "model_limits_enabled": bool(token_usage.get("model_limits_enabled")),
        "models": models,
        "expires_at": expires_at,
        "expires_at_text": "永不过期" if expires_at == 0 else fmt_ts(expires_at),
    }


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _pick_usage_stats(usage_data: dict, key_id: int) -> dict:
    candidates = [
        usage_data.get("stats") if isinstance(usage_data, dict) else None,
        usage_data.get("data") if isinstance(usage_data, dict) else None,
        usage_data,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            value = candidate.get(str(key_id), candidate.get(key_id))
            if isinstance(value, dict):
                return value
    return {}


def build_sub2api_summary(
    user: dict,
    keys_data: dict,
    usage_data: dict | None = None,
    source: dict | None = None,
) -> dict:
    now = int(time.time())
    items = keys_data.get("items") if isinstance(keys_data, dict) else None
    if items is None and isinstance(keys_data, list):
        items = keys_data
    items = items or []
    usage_data = usage_data or {}
    api_keys = []
    for item in items:
        key_id = int(item.get("id", 0) or 0)
        quota = _as_float(item.get("quota"))
        used = _as_float(item.get("quota_used"))
        usage = _pick_usage_stats(usage_data, key_id)
        today_used = _as_float(usage.get("today_actual_cost"))
        total_used = _as_float(usage.get("total_actual_cost"), used)
        if total_used > used:
            used = total_used
        remaining = max(quota - used, 0.0) if quota > 0 else 0.0
        expires_at = item.get("expires_at")
        group = item.get("group") or {}
        api_keys.append(
            {
                "id": key_id,
                "name": item.get("name", ""),
                "status": item.get("status", ""),
                "group": group.get("name", ""),
                "platform": group.get("platform", ""),
                "quota_usd": round(quota, 4),
                "used_usd": round(used, 4),
                "remaining_usd": round(remaining, 4),
                "today_used_usd": round(today_used, 4),
                "rate_limit_5h_usd": _as_float(item.get("rate_limit_5h")),
                "rate_limit_1d_usd": _as_float(item.get("rate_limit_1d")),
                "rate_limit_7d_usd": _as_float(item.get("rate_limit_7d")),
                "expires_at": expires_at,
                "expires_at_text": fmt_ts_from_any(expires_at),
            }
        )
    total_quota = round(sum(k["quota_usd"] for k in api_keys), 4)
    total_used = round(sum(k["used_usd"] for k in api_keys), 4)
    return {
        "fetched_at": now,
        "fetched_at_text": fmt_ts(now),
        "source": source or {},
        "user": {
            "username": user.get("email") or user.get("username"),
            "display_name": user.get("display_name") or user.get("name") or user.get("email"),
            "group": user.get("group") or "",
            "request_count": user.get("request_count") or "",
        },
        "general": {
            "quota": 0,
            "usd": round(total_quota - total_used, 4),
            "used_quota_lifetime": 0,
            "used_usd_lifetime": total_used,
        },
        "api_keys": api_keys,
        "subscriptions": [],
    }


def build_summary(
    self_info: dict,
    sub_info: dict,
    token_usage: dict | None = None,
    source: dict | None = None,
) -> dict:
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

    summary = {
        "fetched_at": now,
        "fetched_at_text": fmt_ts(now),
        "source": source or {},
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
    if token_usage:
        summary["token_usage"] = build_token_usage_summary(token_usage)
    return summary


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
    source = summary.get("source") or {}
    user = summary["user"]
    g = summary["general"]
    lines.append(
        f"{c('bold')}AIu 中转站监控 [{source.get('profile', 'default')}]  ·  {summary['fetched_at_text']}{c('reset')}"
    )
    lines.append(
        f"  用户：{c('cyan')}{user['display_name']}{c('reset')}（{user['username']}）"
        f"  分组：{user['group']}  累计请求：{user['request_count']}"
    )
    lines.append(
        f"  通用额度：{c('bold')}${g['usd']:.2f}{c('reset')}"
        f"   历史消耗：${g['used_usd_lifetime']:.2f}"
    )

    token = summary.get("token_usage")
    if token:
        limit_note = "无限额" if token["unlimited_quota"] else f"剩余 ${token['total_available_usd']:.2f}"
        lines.append(
            f"  API Key：{token['name'] or '未命名'}"
            f"   总 ${token['total_granted_usd']:.2f}"
            f"   已用 ${token['total_used_usd']:.2f}"
            f"   {limit_note}"
            f"   到期：{token['expires_at_text']}"
        )
        if token["model_limits_enabled"] and token["models"]:
            lines.append(f"  模型限制：{', '.join(token['models'])}")

    api_keys = summary.get("api_keys") or []
    if api_keys:
        lines.append("")
        lines.append(f"{c('magenta')}■ API Keys{c('reset')}")
        for key in api_keys:
            quota = key["quota_usd"]
            used = key["used_usd"]
            remaining = key["remaining_usd"]
            if quota > 0:
                quota_text = f"总 ${quota:.2f} 已用 ${used:.2f} 剩余 ${remaining:.2f}"
            else:
                quota_text = "不限总额"
            lines.append(
                f"  #{key['id']} {key['name']} [{key['status']}]"
                f"  今日 ${key['today_used_usd']:.4f}  {quota_text}  到期：{key['expires_at_text']}"
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
def normalize_profile(profile: str) -> str:
    profile = (profile or "").strip().lower()
    if not profile:
        return ""
    return PROFILE_ALIASES.get(profile, profile)


def resolve_profiles(profile: str | None) -> list[str]:
    """Resolve CLI/env profile selection into one or more concrete profiles."""
    raw = (profile or "").strip().lower()
    if not raw or raw in MULTI_PROFILE_ALIASES:
        return list(DEFAULT_QUERY_PROFILES)
    parts = [part.strip() for part in raw.replace("+", ",").split(",") if part.strip()]
    profiles = []
    for part in parts:
        if part in MULTI_PROFILE_ALIASES:
            candidates = DEFAULT_QUERY_PROFILES
        else:
            candidates = (normalize_profile(part),)
        for candidate in candidates:
            if candidate and candidate not in profiles:
                profiles.append(candidate)
    return profiles or list(DEFAULT_QUERY_PROFILES)


def env_prefix(profile: str) -> str:
    return normalize_profile(profile).upper().replace("-", "_")


def first_env(names: list[str]) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def load_env_files() -> None:
    candidates = []
    if os.environ.get("AIU_ENV_FILE"):
        candidates.append(Path(os.environ["AIU_ENV_FILE"]))
    candidates.append(AI_KEYS_ENV)
    if FALLBACK_AI_KEYS_ENV != AI_KEYS_ENV:
        candidates.append(FALLBACK_AI_KEYS_ENV)
    for candidate in candidates:
        load_env(candidate)


def known_profiles() -> dict:
    """Return built-in profile metadata for docs/tests without exposing secrets."""
    return KNOWN_PROFILES.copy()

def resolve_config(args: argparse.Namespace, profile: str | None = None) -> AiuConfig:
    load_env_files()
    selected = profile if profile is not None else args.profile or os.environ.get("AIU_PROFILE", "")
    concrete_profile = normalize_profile(selected) or DEFAULT_QUERY_PROFILES[0]
    prefix = env_prefix(concrete_profile)
    base = first_env([f"{prefix}_BASE", "AIU_BASE"]) or DEFAULT_BASES.get(concrete_profile, "")
    username = first_env([f"{prefix}_USERNAME", "AIU_USERNAME"])
    password = first_env([f"{prefix}_PASSWORD", "AIU_PASSWORD"])
    api_key = first_env([f"{prefix}_API_KEY", f"{prefix}_HERMES_API_KEY", "AIU_API_KEY"])
    interval_raw = first_env([f"{prefix}_INTERVAL", "AIU_INTERVAL", "DSHUB_INTERVAL"])
    interval = args.interval if args.interval is not None else int(interval_raw or 30)
    api_style = first_env([f"{prefix}_API_STYLE", "AIU_API_STYLE"]) or DEFAULT_API_STYLES.get(concrete_profile, "new-api")
    return AiuConfig(concrete_profile, base, username, password, api_key, interval, api_style)


def run_once(client: DshubClient, profile: str = "dshub") -> dict:
    if client.username and client.password:
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
    else:
        self_info = {
            "username": client.username or profile,
            "display_name": client.username or profile,
            "group": "",
            "request_count": "",
            "quota": 0,
            "used_quota": 0,
        }
        sub_info = {}
    token_usage = client.fetch_token_usage() if client.api_key else None
    return build_summary(
        self_info,
        sub_info,
        token_usage=token_usage,
        source={"profile": profile, "base": client.base},
    )


def run_once_sub2api(client: Sub2apiClient, profile: str = "cygces") -> dict:
    if not client.access_token:
        client.login()
    user = client.fetch_me()
    keys_data = client.fetch_keys()
    ids = []
    for item in keys_data.get("items", []) if isinstance(keys_data, dict) else []:
        if item.get("id") is not None:
            ids.append(int(item["id"]))
    usage_data = client.fetch_key_usage(ids) if ids else {}
    return build_sub2api_summary(
        user,
        keys_data,
        usage_data=usage_data,
        source={"profile": profile, "base": client.base},
    )


def create_runner(config: AiuConfig):
    if config.api_style == "sub2api":
        client = Sub2apiClient(config.base, config.username, config.password)
        return lambda: run_once_sub2api(client, config.profile), client
    client = DshubClient(config.base, config.username, config.password, config.api_key)
    return lambda: run_once(client, config.profile), client


def validate_config(config: AiuConfig) -> list[str]:
    errors = []
    prefix = env_prefix(config.profile)
    if not config.base:
        errors.append(f"请设置 {prefix}_BASE")
    if config.api_style == "sub2api" and not (config.username and config.password):
        missing = []
        if not config.username:
            missing.append(f"{prefix}_USERNAME")
        if not config.password:
            missing.append(f"{prefix}_PASSWORD")
        errors.append(f"请设置 {' / '.join(missing)}")
    if config.api_style != "sub2api" and not ((config.username and config.password) or config.api_key):
        errors.append(f"请设置 {prefix}_USERNAME / {prefix}_PASSWORD，或设置 {prefix}_API_KEY")
    return errors


def build_error_summary(profile: str, base: str, error: str) -> dict:
    return {
        "fetched_at": int(time.time()),
        "source": {"profile": profile, "base": base},
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 中转站余额/套餐/API Key 额度监控")
    parser.add_argument("profile_arg", nargs="?", default=None, help="配置 profile；支持 dshub / cygces / all / both，也可逗号分隔")
    parser.add_argument("--profile", default=None, help="配置 profile，例如 dshub / cygces / all / both")
    parser.add_argument("--once", action="store_true", help="只执行一次后退出")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而非可读文本")
    parser.add_argument("--interval", type=int, default=None, help="刷新间隔（秒）")
    parser.add_argument("--no-color", action="store_true", help="禁用 ANSI 颜色")
    parser.add_argument("--no-clear", action="store_true", help="不清屏，每次追加输出")
    args = parser.parse_args()

    # CLI default intentionally ignores AIU_PROFILE so a plain `aiu --once`
    # always checks Aki's two active relays. Pass a profile/alias explicitly
    # when a single relay is needed.
    selected_profile = args.profile or args.profile_arg
    profiles = resolve_profiles(selected_profile)
    configs = [resolve_config(args, profile) for profile in profiles]

    had_config_error = False
    runners = []
    clients = []
    for config in configs:
        errors = validate_config(config)
        if errors:
            had_config_error = True
            for error in errors:
                print(f"错误[{config.profile}]：{error}", file=sys.stderr)
            continue
        runner, client = create_runner(config)
        runners.append((config, runner))
        clients.append(client)

    if not runners:
        return 2

    def emit_all() -> int:
        exit_code = 0
        summaries = []
        for config, runner in runners:
            try:
                summaries.append(runner())
            except (HTTPError, URLError, RuntimeError) as e:
                exit_code = 1
                summaries.append(build_error_summary(config.profile, config.base, str(e)))
        if args.json:
            payload = summaries[0] if len(summaries) == 1 else {"fetched_at": int(time.time()), "profiles": summaries}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            if not args.once and not args.no_clear:
                sys.stdout.write(ANSI["clear"])
            for i, summary in enumerate(summaries):
                if i:
                    print("\n" + "-" * 72 + "\n")
                if summary.get("error"):
                    src = summary.get("source", {})
                    print(f"[{src.get('profile', 'unknown')}] 刷新失败：{summary['error']}")
                else:
                    print(render_text(summary, color=not args.no_color))
            sys.stdout.flush()
        return exit_code

    if args.once:
        return max(emit_all(), 2 if had_config_error else 0)

    profile_names = ", ".join(config.profile for config, _ in runners)
    interval = min(config.interval for config, _ in runners)
    print(f"开始监控 {profile_names} ，每 {interval}s 刷新一次（Ctrl+C 退出）", file=sys.stderr)
    try:
        while True:
            emit_all()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n已停止。", file=sys.stderr)
    for client in clients:
        if hasattr(client, "user_id"):
            client.user_id = None
    return 0


if __name__ == "__main__":
    sys.exit(main())
