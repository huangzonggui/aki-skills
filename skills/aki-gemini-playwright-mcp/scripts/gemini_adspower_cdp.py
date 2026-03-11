#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import websocket


def http_get_json(url: str, timeout: int = 10) -> Any:
    try:
        with urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"HTTP request failed: {url} ({exc})") from exc


class CdpClient:
    def __init__(self, ws_url: str, timeout: int = 30) -> None:
        self.ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
        self._id = 1

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
        req_id = self._id
        self._id += 1
        payload: dict[str, Any] = {"id": req_id, "method": method}
        if params:
            payload["params"] = params
        self.ws.send(json.dumps(payload, ensure_ascii=False))

        deadline = time.time() + max(1, timeout)
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise RuntimeError(f"CDP timeout waiting for: {method}")
            self.ws.settimeout(remaining)
            raw = self.ws.recv()
            msg = json.loads(raw)
            if msg.get("id") != req_id:
                continue
            if "error" in msg:
                err = msg["error"]
                raise RuntimeError(f"CDP error {method}: {err}")
            return msg.get("result", {})

    def evaluate(self, expression: str, timeout: int = 30) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": True,
            },
            timeout=timeout,
        )
        if "exceptionDetails" in result:
            detail = result.get("exceptionDetails", {})
            text = detail.get("text") or "Runtime.evaluate exception"
            exception = detail.get("exception", {})
            desc = exception.get("description") if isinstance(exception, dict) else None
            raise RuntimeError(f"{text}: {desc or ''}".strip())
        obj = result.get("result", {})
        if "value" in obj:
            return obj["value"]
        return None


COLLECT_VISUALS_JS = r"""
(() => {
  const minSize = 96;
  const out = [];

  const images = Array.from(document.querySelectorAll('img'));
  for (const img of images) {
    const w = img.naturalWidth || img.width || 0;
    const h = img.naturalHeight || img.height || 0;
    if (w < minSize || h < minSize) continue;
    const src = img.currentSrc || img.src || '';
    if (!src) continue;
    const rect = img.getBoundingClientRect();
    out.push({
      key: `img:${src}|${w}x${h}`,
      src,
      score: w * h,
      y: rect.top + window.scrollY,
    });
  }

  const canvases = Array.from(document.querySelectorAll('canvas'));
  canvases.forEach((canvas, idx) => {
    const w = canvas.width || 0;
    const h = canvas.height || 0;
    if (w < minSize || h < minSize) return;
    try {
      const dataUrl = canvas.toDataURL('image/png');
      if (!dataUrl) return;
      const rect = canvas.getBoundingClientRect();
      out.push({
        key: `canvas:${idx}|${w}x${h}|${dataUrl.slice(0, 128)}`,
        src: dataUrl,
        score: w * h,
        y: rect.top + window.scrollY,
      });
    } catch (_) {
    }
  });

  const bgNodes = Array.from(document.querySelectorAll('[style*="background-image"], [role="img"]'));
  for (const node of bgNodes) {
    const rect = node.getBoundingClientRect();
    const w = Math.round(rect.width || 0);
    const h = Math.round(rect.height || 0);
    if (w < minSize || h < minSize) continue;
    const style = getComputedStyle(node);
    const bg = style.backgroundImage || '';
    if (!bg || bg === 'none') continue;
    const m = bg.match(/url\((['"]?)(.*?)\1\)/i);
    const src = (m?.[2] || '').trim();
    if (!src) continue;
    out.push({
      key: `bg:${src}|${w}x${h}`,
      src,
      score: w * h,
      y: rect.top + window.scrollY,
    });
  }

  return out;
})()
"""


def build_send_prompt_js(prompt: str) -> str:
    prompt_json = json.dumps(prompt, ensure_ascii=False)
    return f"""
(() => {{
  const prompt = {prompt_json};
  const clickByText = (texts) => {{
    const nodes = Array.from(document.querySelectorAll('button, div[role="button"]'));
    for (const node of nodes) {{
      const text = (node.innerText || node.textContent || '').trim();
      if (!text) continue;
      if (texts.some((x) => text === x || text.includes(x))) {{
        node.click();
        return true;
      }}
    }}
    return false;
  }};

  clickByText(['Image', 'Images', 'Create image', 'Generate image', '制作图片', '图片', '图像', '生成图像']);

  const input = document.querySelector('textarea, div[contenteditable="true"]');
  if (!input) return {{ ok: false, error: 'composer not found', url: location.href }};

  input.focus();
  if ((input.tagName || '').toLowerCase() === 'textarea') {{
    input.value = prompt;
    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }} else {{
    input.textContent = prompt;
    input.dispatchEvent(new InputEvent('input', {{ bubbles: true, data: prompt, inputType: 'insertText' }}));
  }}

  const submitSelectors = [
    'button[type="submit"]',
    'form button[type="submit"]',
    'button[aria-label*="send" i]',
    'button[aria-label*="发送"]',
    'button[aria-label="Send message"]',
    'button[aria-label="发送消息"]',
    'div[role="button"][aria-label="Send message"]',
    'div[role="button"][aria-label="发送消息"]',
  ];
  let clicked = false;
  for (const sel of submitSelectors) {{
    const btn = document.querySelector(sel);
    if (btn) {{
      btn.click();
      clicked = true;
      break;
    }}
  }}
  if (!clicked) {{
    clicked = clickByText(['Send', '发送', '发送消息']);
  }}

  if (!clicked) {{
    input.dispatchEvent(new KeyboardEvent('keydown', {{
      key: 'Enter',
      code: 'Enter',
      metaKey: true,
      bubbles: true,
      cancelable: true
    }}));
    input.dispatchEvent(new KeyboardEvent('keyup', {{
      key: 'Enter',
      code: 'Enter',
      metaKey: true,
      bubbles: true,
      cancelable: true
    }}));
  }}

  return {{ ok: true, clicked, url: location.href }};
}})()
"""


def build_fetch_b64_js(src: str) -> str:
    src_json = json.dumps(src, ensure_ascii=False)
    return f"""
(async () => {{
  const src = {src_json};
  if (src.startsWith('data:')) {{
    const idx = src.indexOf(',');
    return idx >= 0 ? src.slice(idx + 1) : '';
  }}
  const res = await fetch(src);
  const blob = await res.blob();
  const dataUrl = await new Promise((resolve, reject) => {{
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('FileReader error'));
    reader.readAsDataURL(blob);
  }});
  const idx = dataUrl.indexOf(',');
  return idx >= 0 ? dataUrl.slice(idx + 1) : '';
}})()
"""


def pick_best_candidate(items: list[dict[str, Any]], before_keys: set[str]) -> str:
    fresh = [x for x in items if str(x.get("key", "")) not in before_keys and str(x.get("src", ""))]
    pool = fresh if fresh else [x for x in items if str(x.get("src", ""))]
    if not pool:
        return ""

    def rank(item: dict[str, Any]) -> int:
        src = str(item.get("src", "")).lower()
        if src.startswith("data:") or src.startswith("blob:"):
            return 6
        if "lh3.googleusercontent.com" in src and ("gg-dl/" in src or "rd-gg-dl/" in src):
            return 5
        if "googleusercontent.com" in src:
            return 4
        if src.startswith("http://") or src.startswith("https://"):
            if "gstatic.com" in src:
                return 1
            return 2
        return 0

    preferred = [x for x in pool if rank(x) >= 4 and float(x.get("score", 0)) >= 512 * 512]
    if preferred:
        pool = preferred
    else:
        medium = [x for x in pool if rank(x) >= 3 and float(x.get("score", 0)) >= 256 * 256]
        if medium:
            pool = medium
        else:
            return ""

    pool.sort(
        key=lambda x: (
            rank(x),
            float(x.get("y", 0)),
            float(x.get("score", 0)),
        ),
        reverse=True,
    )
    return str(pool[0].get("src", ""))


def decode_b64_payload(data: str) -> bytes:
    payload = (data or "").strip()
    if not payload:
        raise RuntimeError("Empty base64 payload.")
    pad = (-len(payload)) % 4
    if pad:
        payload += "=" * pad
    return base64.b64decode(payload)


def download_http_image(url: str, timeout: int = 60) -> bytes:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def wait_document_complete(client: CdpClient, timeout_sec: int = 20) -> bool:
    deadline = time.time() + max(1, timeout_sec)
    while time.time() < deadline:
        try:
            state = client.evaluate("document.readyState", timeout=5)
            if state == "complete":
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def capture_http_image_via_navigation(
    client: CdpClient,
    source_page_url: str,
    image_url: str,
    output_path: Path,
) -> bool:
    if not (image_url.startswith("http://") or image_url.startswith("https://")):
        return False

    def _image_rect() -> dict[str, Any] | None:
        js = r"""
(() => {
  const img = document.querySelector('img');
  if (!img) return null;
  const r = img.getBoundingClientRect();
  return {
    x: Math.max(0, r.x),
    y: Math.max(0, r.y),
    width: Math.max(1, r.width),
    height: Math.max(1, r.height),
    naturalWidth: img.naturalWidth || 0,
    naturalHeight: img.naturalHeight || 0,
  };
})()
"""
        rect = client.evaluate(js, timeout=10)
        return rect if isinstance(rect, dict) else None

    try:
        client.call("Page.navigate", {"url": image_url}, timeout=30)
    except Exception:
        return False

    try:
        wait_document_complete(client, timeout_sec=20)
        try:
            # Remove default margins so clip matches the actual image area.
            client.evaluate(
                r"""
(() => {
  const css = 'html,body{margin:0!important;padding:0!important;}img{display:block!important;margin:0!important;}';
  const id = '__aki_image_extract_style__';
  let style = document.getElementById(id);
  if (!style) {
    style = document.createElement('style');
    style.id = id;
    style.textContent = css;
    (document.head || document.documentElement).appendChild(style);
  }
  return true;
})()
""",
                timeout=10,
            )
        except Exception:
            pass

        rect = _image_rect()
        if rect and rect.get("naturalWidth") and rect.get("naturalHeight"):
            width = int(rect["naturalWidth"])
            height = int(rect["naturalHeight"])
            width = max(64, min(4096, width))
            height = max(64, min(4096, height))
            try:
                client.call(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                    timeout=10,
                )
                time.sleep(0.2)
                rect = _image_rect() or rect
            except Exception:
                pass

        if not rect or not rect.get("width") or not rect.get("height"):
            return False

        capture = client.call(
            "Page.captureScreenshot",
            {
                "format": "png",
                "captureBeyondViewport": True,
                "clip": {
                    "x": float(rect["x"]),
                    "y": float(rect["y"]),
                    "width": float(rect["width"]),
                    "height": float(rect["height"]),
                    "scale": 1,
                },
            },
            timeout=30,
        )
        data = capture.get("data")
        if not isinstance(data, str) or not data:
            return False
        output_path.write_bytes(base64.b64decode(data))
        return True
    finally:
        try:
            client.call("Emulation.clearDeviceMetricsOverride", timeout=10)
        except Exception:
            pass
        if source_page_url:
            try:
                client.call("Page.navigate", {"url": source_page_url}, timeout=20)
                wait_document_complete(client, timeout_sec=15)
            except Exception:
                pass


def screenshot_fallback(client: CdpClient, output_path: Path, src: str) -> bool:
    precise_js = _deprecated_old_screenshot_locator(src)
    precise = client.evaluate(precise_js, timeout=30)
    if isinstance(precise, dict) and precise.get("width") and precise.get("height"):
        capture = client.call(
            "Page.captureScreenshot",
            {
                "format": "png",
                "captureBeyondViewport": True,
                "clip": {
                    "x": float(precise["x"]),
                    "y": float(precise["y"]),
                    "width": float(precise["width"]),
                    "height": float(precise["height"]),
                    "scale": 1,
                },
            },
            timeout=30,
        )
        data = capture.get("data")
        if isinstance(data, str) and data:
            output_path.write_bytes(base64.b64decode(data))
            return True

    locate_js = f"""
(() => {{
  window.scrollTo(0, document.body.scrollHeight);
  const candidates = Array.from(document.querySelectorAll('img, canvas, [style*="background-image"], [role="img"]'));
  let el = null;
  let bestScore = -1;
  for (const node of candidates) {{
    const rect0 = node.getBoundingClientRect();
    const w0 = Math.round(rect0.width || 0);
    const h0 = Math.round(rect0.height || 0);
    if (w0 < 256 || h0 < 256) continue;
    const visible = getComputedStyle(node).display !== 'none' && getComputedStyle(node).visibility !== 'hidden';
    if (!visible) continue;
    const area = w0 * h0;
    const score = area + (rect0.top + window.scrollY);
    if (score > bestScore) {{
      bestScore = score;
      el = node;
    }}
  }}

  if (!el) {{
    for (const node of candidates) {{
      const rect0 = node.getBoundingClientRect();
      const w0 = Math.round(rect0.width || 0);
      const h0 = Math.round(rect0.height || 0);
      if (w0 < 96 || h0 < 96) continue;
      el = node;
      break;
    }}
  }}

  if (!el) return null;
  el.scrollIntoView({{ block: 'center', inline: 'center' }});
  const r = el.getBoundingClientRect();
  return {{
    x: Math.max(0, r.x),
    y: Math.max(0, r.y),
    width: Math.max(1, r.width),
    height: Math.max(1, r.height),
    tag: (el.tagName || '').toLowerCase(),
  }};
}})()
"""
    rect = client.evaluate(locate_js, timeout=30)
    if isinstance(rect, dict) and rect.get("width") and rect.get("height"):
        capture = client.call(
            "Page.captureScreenshot",
            {
                "format": "png",
                "captureBeyondViewport": True,
                "clip": {
                    "x": float(rect["x"]),
                    "y": float(rect["y"]),
                    "width": float(rect["width"]),
                    "height": float(rect["height"]),
                    "scale": 1,
                },
            },
            timeout=30,
        )
        data = capture.get("data")
        if isinstance(data, str) and data:
            output_path.write_bytes(base64.b64decode(data))
            return True

    capture = client.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True}, timeout=30)
    data = capture.get("data")
    if isinstance(data, str) and data:
        output_path.write_bytes(base64.b64decode(data))
        return True
    return False


def _deprecated_old_screenshot_locator(src: str) -> str:
    src_json = json.dumps(src, ensure_ascii=False)
    return f"""
(() => {{
  const src = {src_json};
  const candidates = Array.from(document.querySelectorAll('img, canvas, [style*="background-image"], [role="img"]'));
  let el = null;
  for (const node of candidates) {{
    if (node.tagName === 'IMG') {{
      const s = node.currentSrc || node.src || '';
      if (s === src) {{ el = node; break; }}
      continue;
    }}
    if (node.tagName === 'CANVAS' && src.startsWith('data:')) {{
      try {{
        const d = node.toDataURL('image/png');
        if (d && d.slice(0, 128) === src.slice(0, 128)) {{ el = node; break; }}
      }} catch (_) {{}}
      continue;
    }}
    const style = getComputedStyle(node);
    const bg = style.backgroundImage || '';
    const m = bg.match(/url\\((['"]?)(.*?)\\1\\)/i);
    const s = (m?.[2] || '').trim();
    if (s && s === src) {{ el = node; break; }}
  }}
  if (!el) return null;
  el.scrollIntoView({{ block: 'center', inline: 'center' }});
  const r = el.getBoundingClientRect();
  return {{
    x: Math.max(0, r.x),
    y: Math.max(0, r.y),
    width: Math.max(1, r.width),
    height: Math.max(1, r.height),
  }};
}})()
"""


def find_gemini_page_ws(cdp_base: str) -> str:
    listing = http_get_json(f"{cdp_base.rstrip('/')}/json/list")
    if not isinstance(listing, list):
        raise RuntimeError("Invalid /json/list response.")
    for item in listing:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "page":
            continue
        url = str(item.get("url", ""))
        if "gemini.google.com/app" in url:
            ws_url = str(item.get("webSocketDebuggerUrl", "")).strip()
            if ws_url:
                return ws_url
    raise RuntimeError("Gemini page not found in AdsPower browser. Open https://gemini.google.com/app first.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Gemini images through AdsPower CDP (browser-only).")
    parser.add_argument("--prompt", default="", help="Prompt text")
    parser.add_argument("--prompt-file", default="", help="Prompt file path")
    parser.add_argument("--out", required=True, help="Output image path")
    parser.add_argument("--cdp-base", default="http://127.0.0.1:52922", help="CDP base URL (e.g. http://127.0.0.1:52922)")
    parser.add_argument("--timeout", type=int, default=240, help="Timeout seconds")
    args = parser.parse_args()

    prompt = (args.prompt or "").strip()
    if not prompt and args.prompt_file:
        prompt = Path(args.prompt_file).expanduser().read_text(encoding="utf-8", errors="replace").strip()
    if not prompt:
        raise SystemExit("Missing --prompt or --prompt-file.")

    page_ws = find_gemini_page_ws(args.cdp_base)
    print(f"[AdsPower CDP] Gemini page: {page_ws}")
    client = CdpClient(page_ws, timeout=30)
    try:
        before = client.evaluate(COLLECT_VISUALS_JS, timeout=20) or []
        before_keys = {str(x.get("key", "")) for x in before if isinstance(x, dict)}
        print(f"[AdsPower CDP] Existing visuals: {len(before_keys)}")

        sent = client.evaluate(build_send_prompt_js(prompt), timeout=30) or {}
        if not isinstance(sent, dict) or not sent.get("ok"):
            raise RuntimeError(f"Failed to send prompt: {sent}")
        source_page_url = str(sent.get("url") or "https://gemini.google.com/app")
        print("[AdsPower CDP] Prompt submitted.")

        deadline = time.time() + max(30, args.timeout)
        image_src = ""
        tick = 0
        while time.time() < deadline:
            time.sleep(2)
            items = client.evaluate(COLLECT_VISUALS_JS, timeout=20) or []
            if not isinstance(items, list):
                continue
            image_src = pick_best_candidate(items, before_keys)
            if image_src:
                break
            tick += 1
            if tick % 5 == 0:
                print(f"[AdsPower CDP] Waiting image... seen={len(items)}")

        if not image_src:
            raise RuntimeError("No generated image detected before timeout.")
        print(f"[AdsPower CDP] Picked src: {image_src[:120]}")

        out_path = Path(args.out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        raw: bytes
        if image_src.startswith("data:"):
            raw = decode_b64_payload(image_src.split(",", 1)[1] if "," in image_src else image_src)
            out_path.write_bytes(raw)
        elif image_src.startswith("http://") or image_src.startswith("https://"):
            try:
                raw = download_http_image(image_src, timeout=90)
                out_path.write_bytes(raw)
            except Exception:
                print("[AdsPower CDP] HTTP download failed, trying browser navigation capture.")
                if capture_http_image_via_navigation(client, source_page_url, image_src, out_path):
                    raw = out_path.read_bytes()
                else:
                    print("[AdsPower CDP] Browser navigation capture failed, trying in-page fetch.")
                    try:
                        b64_payload = client.evaluate(build_fetch_b64_js(image_src), timeout=90)
                        if not isinstance(b64_payload, str) or not b64_payload:
                            raise RuntimeError("Empty fetch payload")
                        raw = decode_b64_payload(b64_payload)
                        out_path.write_bytes(raw)
                    except Exception:
                        print("[AdsPower CDP] In-page fetch failed, falling back to screenshot.")
                        if not screenshot_fallback(client, out_path, image_src):
                            raise RuntimeError("Image download failed and screenshot fallback also failed.")
        else:
            try:
                b64_payload = client.evaluate(build_fetch_b64_js(image_src), timeout=45)
                if not isinstance(b64_payload, str) or not b64_payload:
                    raise RuntimeError("Empty fetch payload")
                raw = decode_b64_payload(b64_payload)
                out_path.write_bytes(raw)
            except Exception:
                print("[AdsPower CDP] Blob/data fetch failed, falling back to screenshot.")
                if not screenshot_fallback(client, out_path, image_src):
                    raise RuntimeError("Blob fetch failed and screenshot fallback also failed.")

        print(f"Image generated: {out_path}")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
