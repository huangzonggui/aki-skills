#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


COMFLY_CONFIG = Path.home() / ".config" / "comfly" / "config"
KEYS_ENV = Path("/Users/aki/.config/ai/keys.env")
DEFAULT_BASE = "https://ai.comfly.chat"
CHAT_PATH = "/v1/chat/completions"
DEFAULT_MODEL = "gemini-3-pro-preview-thinking"


def _parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        key = k.strip()
        value = v.strip().strip('"').strip("'")
        if key:
            data[key] = value
    return data


def _normalize_chat_url(raw: str) -> str:
    value = raw.strip()
    if not value:
        value = DEFAULT_BASE
    if value.endswith(CHAT_PATH):
        return value
    return value.rstrip("/") + CHAT_PATH


def resolve_config(model_override: str = "") -> dict[str, str]:
    file_cfg = _parse_env_file(COMFLY_CONFIG)
    keys_cfg = _parse_env_file(KEYS_ENV)
    api_key = (
        os.getenv("COMFLY_API_KEY")
        or keys_cfg.get("COMFLY_API_KEY")
        or file_cfg.get("COMFLY_API_KEY")
        or file_cfg.get("API_KEY")
        or ""
    ).strip()
    if not api_key:
        raise RuntimeError(f"Missing COMFLY_API_KEY (set env or {COMFLY_CONFIG})")

    raw_url = (
        os.getenv("COMFLY_API_URL")
        or keys_cfg.get("COMFLY_API_URL")
        or file_cfg.get("COMFLY_API_URL")
        or os.getenv("COMFLY_API_BASE_URL")
        or keys_cfg.get("COMFLY_API_BASE_URL")
        or file_cfg.get("COMFLY_API_BASE_URL")
        or ""
    ).strip()
    api_url = _normalize_chat_url(raw_url)

    model = (
        model_override.strip()
        or os.getenv("COMFLY_CHAT_MODEL")
        or keys_cfg.get("COMFLY_CHAT_MODEL")
        or os.getenv("COMFLY_MODEL")
        or keys_cfg.get("COMFLY_MODEL")
        or file_cfg.get("COMFLY_CHAT_MODEL")
        or file_cfg.get("COMFLY_MODEL")
        or DEFAULT_MODEL
    ).strip()
    return {"api_key": api_key, "api_url": api_url, "model": model}


def chat_complete(
    system_prompt: str,
    user_prompt: str,
    model_override: str = "",
    temperature: float = 0.6,
) -> str:
    cfg = resolve_config(model_override)
    payload: dict[str, Any] = {
        "model": cfg["model"],
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    req = Request(
        url=cfg["api_url"],
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
            "User-Agent": "aki-content-pipeline-pro/1.0",
        },
    )
    with urlopen(req, timeout=180) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Empty chat response: {raw[:400]}")
    content = (((choices[0] or {}).get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("Chat response contains empty content")
    return content
