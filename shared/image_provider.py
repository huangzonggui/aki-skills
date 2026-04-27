from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from http.client import IncompleteRead
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aki_runtime import default_ai_keys_env_path


DEFAULT_COMFLY_CONFIG_PATH = Path.home() / ".config" / "comfly" / "config"
DEFAULT_COMFLY_BASE_URL = "https://ai.comfly.chat"
DEFAULT_COMFLY_PATH = "/v1/images/generations"
DEFAULT_OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_IMAGE_MODEL = "google/gemini-3.1-flash-image-preview"
DEFAULT_ASPECT_RATIO = "3:4"
TRANSIENT_HTTP_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class ImageRenderRequest:
    prompt: str
    output_path: Path


@dataclass(frozen=True)
class ImageRenderResult:
    output_path: Path
    provider_used: str
    image_format: str


@dataclass(frozen=True)
class ImageBatchResult:
    provider_used: str
    fallback_triggered: bool
    rendered_images: list[ImageRenderResult]
    provider_billed_images: dict[str, int]


class ImageProviderError(RuntimeError):
    def __init__(
        self,
        *,
        provider: str,
        category: str,
        message: str,
        recoverable: bool,
        status_code: int | None = None,
        billed_images: int = 0,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.category = category
        self.recoverable = recoverable
        self.status_code = status_code
        self.billed_images = billed_images


def parse_env_like_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        data[key] = value.strip().strip("'\"")
    return data


def normalize_base_url(raw_url: str) -> str:
    url = raw_url.strip().rstrip("/")
    if not url:
        return ""
    suffixes = (
        "/v1/chat/completions",
        "/chat/completions",
        "/api/v1/chat/completions",
        "/v1/images/generations",
        "/images/generations",
    )
    for suffix in suffixes:
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url


def normalize_openrouter_api_url(raw_url: str) -> str:
    value = raw_url.strip().rstrip("/")
    if not value:
        return DEFAULT_OPENROUTER_API_URL
    if value.endswith("/api/v1/chat/completions") or value.endswith("/chat/completions"):
        return value
    if value.endswith("/api/v1"):
        return value + "/chat/completions"
    if value.endswith("/v1"):
        return value + "/chat/completions"
    return value + "/api/v1/chat/completions"


def infer_openrouter_image_size(raw_model: str, configured_size: str) -> str:
    if configured_size.strip():
        return configured_size.strip()
    model = raw_model.strip().lower()
    if "4k" in model:
        return "4K"
    if "0.5k" in model or "half" in model:
        return "0.5K"
    return "2K"


def load_provider_configs() -> dict[str, dict[str, Any]]:
    config_file = parse_env_like_file(DEFAULT_COMFLY_CONFIG_PATH)
    keys_file = parse_env_like_file(default_ai_keys_env_path())

    configs: dict[str, dict[str, Any]] = {}

    comfly_api_key = (
        os.getenv("COMFLY_API_KEY")
        or keys_file.get("COMFLY_API_KEY")
        or config_file.get("COMFLY_API_KEY")
        or ""
    ).strip()
    comfly_base = normalize_base_url(
        (
            os.getenv("COMFLY_API_BASE_URL")
            or os.getenv("COMFLY_API_URL")
            or keys_file.get("COMFLY_API_BASE_URL")
            or keys_file.get("COMFLY_API_URL")
            or config_file.get("COMFLY_API_BASE_URL")
            or config_file.get("COMFLY_API_URL")
            or DEFAULT_COMFLY_BASE_URL
        ).strip()
    )
    comfly_model = (
        os.getenv("COMFLY_IMAGE_MODEL")
        or keys_file.get("COMFLY_IMAGE_MODEL")
        or config_file.get("COMFLY_IMAGE_MODEL")
        or ""
    ).strip()
    if comfly_api_key and comfly_model:
        configs["comfly"] = {
            "base_url": comfly_base,
            "path": DEFAULT_COMFLY_PATH,
            "api_key": comfly_api_key,
            "image_model": comfly_model,
            "auth_header": "Authorization",
            "auth_prefix": "Bearer ",
            "timeout_sec": int(
                (
                    os.getenv("COMFLY_IMAGE_TIMEOUT_SEC")
                    or keys_file.get("COMFLY_IMAGE_TIMEOUT_SEC")
                    or config_file.get("COMFLY_IMAGE_TIMEOUT_SEC")
                    or "120"
                ).strip()
            ),
            "aspect_ratio": DEFAULT_ASPECT_RATIO,
            "image_size": "",
            "size": (
                os.getenv("COMFLY_IMAGE_SIZE")
                or keys_file.get("COMFLY_IMAGE_SIZE")
                or config_file.get("COMFLY_IMAGE_SIZE")
                or ""
            ).strip(),
            "quality": (
                os.getenv("COMFLY_IMAGE_QUALITY")
                or keys_file.get("COMFLY_IMAGE_QUALITY")
                or config_file.get("COMFLY_IMAGE_QUALITY")
                or ""
            ).strip(),
            "image": [],
            "accept_language": "zh-CN",
            "extra_body": {},
        }

    openrouter_api_key = (
        os.getenv("OPENROUTER_API_KEY")
        or keys_file.get("OPENROUTER_API_KEY")
        or config_file.get("OPENROUTER_API_KEY")
        or ""
    ).strip()
    openrouter_model = (
        os.getenv("OPENROUTER_IMAGE_MODEL")
        or keys_file.get("OPENROUTER_IMAGE_MODEL")
        or config_file.get("OPENROUTER_IMAGE_MODEL")
        or DEFAULT_OPENROUTER_IMAGE_MODEL
    ).strip()
    openrouter_api_url = normalize_openrouter_api_url(
        (
            os.getenv("OPENROUTER_API_URL")
            or os.getenv("OPENROUTER_API_BASE_URL")
            or keys_file.get("OPENROUTER_API_URL")
            or keys_file.get("OPENROUTER_API_BASE_URL")
            or config_file.get("OPENROUTER_API_URL")
            or config_file.get("OPENROUTER_API_BASE_URL")
            or ""
        ).strip()
    )
    openrouter_size = infer_openrouter_image_size(
        comfly_model,
        (
            os.getenv("OPENROUTER_IMAGE_SIZE")
            or keys_file.get("OPENROUTER_IMAGE_SIZE")
            or config_file.get("OPENROUTER_IMAGE_SIZE")
            or ""
        ).strip(),
    )
    if openrouter_api_key:
        configs["openrouter"] = {
            "api_url": openrouter_api_url,
            "api_key": openrouter_api_key,
            "image_model": openrouter_model,
            "aspect_ratio": DEFAULT_ASPECT_RATIO,
            "image_size": openrouter_size,
            "timeout_sec": int(
                (
                    os.getenv("OPENROUTER_IMAGE_TIMEOUT_SEC")
                    or keys_file.get("OPENROUTER_IMAGE_TIMEOUT_SEC")
                    or config_file.get("OPENROUTER_IMAGE_TIMEOUT_SEC")
                    or "180"
                ).strip()
            ),
            "app_name": (
                os.getenv("OPENROUTER_APP_NAME")
                or keys_file.get("OPENROUTER_APP_NAME")
                or config_file.get("OPENROUTER_APP_NAME")
                or ""
            ).strip(),
            "site_url": (
                os.getenv("OPENROUTER_SITE_URL")
                or keys_file.get("OPENROUTER_SITE_URL")
                or config_file.get("OPENROUTER_SITE_URL")
                or ""
            ).strip(),
        }
    return configs


def load_comfly_settings() -> dict[str, Any]:
    configs = load_provider_configs()
    if "comfly" not in configs:
        raise ImageProviderError(
            provider="comfly",
            category="config",
            message=f"Missing Comfly config. Set COMFLY_API_KEY and COMFLY_IMAGE_MODEL in {default_ai_keys_env_path()} or {DEFAULT_COMFLY_CONFIG_PATH}.",
            recoverable=False,
        )
    return dict(configs["comfly"])


def _build_auth_headers(config: dict[str, Any]) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        str(config.get("auth_header") or "Authorization"): (
            f"{str(config.get('auth_prefix') or 'Bearer ')}{config['api_key']}"
        ),
    }
    if config.get("accept_language"):
        headers["Accept-Language"] = str(config["accept_language"])
    return headers


def build_comfly_request(prompt: str, config: dict[str, Any]) -> tuple[str, dict[str, str], dict[str, Any], int]:
    base_url = str(config.get("base_url") or "").rstrip("/")
    if not base_url:
        raise ImageProviderError(
            provider="comfly",
            category="config",
            message="Missing Comfly base URL.",
            recoverable=False,
        )
    path = str(config.get("path") or DEFAULT_COMFLY_PATH)
    if not path.startswith("/"):
        path = "/" + path
    headers = _build_auth_headers(config)
    payload: dict[str, Any] = {
        "model": str(config.get("image_model") or "").strip(),
        "prompt": prompt,
        "response_format": "b64_json",
    }
    if config.get("aspect_ratio"):
        payload["aspect_ratio"] = config["aspect_ratio"]
    if config.get("image_size"):
        payload["image_size"] = config["image_size"]
    if config.get("size"):
        payload["size"] = config["size"]
    if config.get("quality"):
        payload["quality"] = config["quality"]
    if config.get("image"):
        payload["image"] = config["image"]
    extra_body = config.get("extra_body") or {}
    if isinstance(extra_body, dict):
        payload.update(extra_body)
    if not str(payload["model"]).strip():
        raise ImageProviderError(
            provider="comfly",
            category="config",
            message="Missing Comfly image model.",
            recoverable=False,
        )
    return base_url + path, headers, payload, int(config.get("timeout_sec") or 120)


def build_openrouter_request(prompt: str, config: dict[str, Any]) -> tuple[str, dict[str, str], dict[str, Any], int]:
    api_url = str(config.get("api_url") or "").strip()
    api_key = str(config.get("api_key") or "").strip()
    image_model = str(config.get("image_model") or "").strip()
    if not api_url or not api_key or not image_model:
        raise ImageProviderError(
            provider="openrouter",
            category="config",
            message="Missing OpenRouter image provider config.",
            recoverable=False,
        )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if str(config.get("app_name") or "").strip():
        headers["X-Title"] = str(config["app_name"]).strip()
    if str(config.get("site_url") or "").strip():
        headers["HTTP-Referer"] = str(config["site_url"]).strip()
    payload: dict[str, Any] = {
        "model": image_model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
        "image_config": {
            "aspect_ratio": str(config.get("aspect_ratio") or DEFAULT_ASPECT_RATIO),
            "image_size": str(config.get("image_size") or "2K"),
        },
        "stream": False,
    }
    return api_url, headers, payload, int(config.get("timeout_sec") or 180)


def mask_sensitive_headers(headers: dict[str, str]) -> dict[str, str]:
    masked: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in {"authorization", "x-api-key", "api-key"}:
            masked[key] = "***masked***"
        else:
            masked[key] = value
    return masked


def build_request_preview(
    provider: str,
    prompt: str,
    config: dict[str, Any],
) -> tuple[str, dict[str, str], dict[str, Any], int]:
    if provider == "comfly":
        return build_comfly_request(prompt, config)
    if provider == "openrouter":
        return build_openrouter_request(prompt, config)
    raise ValueError(f"Unsupported provider: {provider}")


def _curl_request_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int, provider: str) -> Any:
    cmd = ["curl", "--http1.1", "-sS", "-X", "POST", url, "--max-time", str(timeout)]
    for key, value in headers.items():
        cmd.extend(["-H", f"{key}: {value}"])
    cmd.extend(["-d", json.dumps(payload, ensure_ascii=False)])
    cp = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if cp.returncode != 0:
        raise ImageProviderError(
            provider=provider,
            category="transient",
            message=cp.stderr.strip() or cp.stdout.strip() or f"{provider} curl request failed",
            recoverable=True,
        )
    try:
        return json.loads(cp.stdout)
    except json.JSONDecodeError as exc:
        raise ImageProviderError(
            provider=provider,
            category="transient",
            message=f"{provider} returned invalid JSON via curl: {cp.stdout[:400]}",
            recoverable=True,
        ) from exc


def request_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: int,
    provider: str,
) -> Any:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        recoverable = exc.code in TRANSIENT_HTTP_CODES
        category = "transient" if recoverable else "request"
        raise ImageProviderError(
            provider=provider,
            category=category,
            message=f"{provider} API error {exc.code}: {detail}",
            recoverable=recoverable,
            status_code=exc.code,
        ) from exc
    except (URLError, TimeoutError, IncompleteRead) as exc:
        return _curl_request_json(url, headers, payload, timeout, provider)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImageProviderError(
            provider=provider,
            category="transient",
            message=f"{provider} returned invalid JSON: {raw[:400]}",
            recoverable=True,
        ) from exc


def extract_comfly_image_payload(response: Any) -> tuple[str, str]:
    if not isinstance(response, dict):
        raise ImageProviderError(
            provider="comfly",
            category="response",
            message="Comfly response is not a JSON object.",
            recoverable=True,
        )
    data = response.get("data") or response.get("images") or response.get("output")
    if isinstance(data, dict):
        items = [data]
    elif isinstance(data, list):
        items = list(data)
    else:
        items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("b64_json"), str):
            return "b64", item["b64_json"]
        if isinstance(item.get("base64"), str):
            return "b64", item["base64"]
        if isinstance(item.get("url"), str):
            return "url", item["url"]
    raise ImageProviderError(
        provider="comfly",
        category="response",
        message="Comfly response contains no image payload.",
        recoverable=True,
    )


def extract_openrouter_image_payload(response: Any) -> tuple[str, str]:
    if not isinstance(response, dict):
        raise ImageProviderError(
            provider="openrouter",
            category="response",
            message="OpenRouter response is not a JSON object.",
            recoverable=True,
        )
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ImageProviderError(
            provider="openrouter",
            category="response",
            message="OpenRouter response contains no choices.",
            recoverable=True,
        )
    message = (choices[0] or {}).get("message") or {}
    images = message.get("images") or []
    if not isinstance(images, list) or not images:
        raise ImageProviderError(
            provider="openrouter",
            category="response",
            message="OpenRouter response contains no generated images.",
            recoverable=True,
        )
    image = images[0] or {}
    image_url = image.get("image_url") or image.get("imageUrl") or {}
    if not isinstance(image_url, dict) or not isinstance(image_url.get("url"), str):
        raise ImageProviderError(
            provider="openrouter",
            category="response",
            message="OpenRouter response contains invalid image payload.",
            recoverable=True,
        )
    url = image_url["url"]
    return ("b64", url) if url.startswith("data:") else ("url", url)


def decode_base64_image_payload(data: str) -> bytes:
    payload = data.strip()
    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1]
    payload = re.sub(r"\s+", "", payload).replace("-", "+").replace("_", "/")
    payload = re.sub(r"[^A-Za-z0-9+/=]", "", payload)
    if not payload:
        raise RuntimeError("Empty base64 image payload.")
    padding = (-len(payload)) % 4
    if padding:
        payload += "=" * padding
    return base64.b64decode(payload, validate=False)


def _curl_download(url: str, timeout: int, user_agent: str, provider: str) -> bytes:
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        temp_path = Path(tmp.name)
    try:
        cp = subprocess.run(
            [
                "curl",
                "--http1.1",
                "-sSL",
                "--retry",
                "4",
                "--retry-all-errors",
                "--retry-delay",
                "2",
                "--max-time",
                str(timeout),
                "-H",
                f"User-Agent: {user_agent}",
                "-o",
                str(temp_path),
                url,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if cp.returncode != 0:
            raise ImageProviderError(
                provider=provider,
                category="transient",
                message=cp.stderr.strip() or cp.stdout.strip() or f"{provider} image download failed",
                recoverable=True,
            )
        return temp_path.read_bytes()
    finally:
        temp_path.unlink(missing_ok=True)


def download_image(url: str, timeout: int, user_agent: str, provider: str) -> bytes:
    req = Request(url, headers={"User-Agent": user_agent})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (URLError, TimeoutError) as exc:
        return _curl_download(url, timeout, user_agent, provider)


def normalize_image_bytes(raw: bytes) -> tuple[bytes, int]:
    if not raw:
        return raw, 0

    def is_webp_at(data: bytes, idx: int) -> bool:
        return idx + 12 <= len(data) and data[idx : idx + 4] == b"RIFF" and data[idx + 8 : idx + 12] == b"WEBP"

    signatures = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a")
    for sig in signatures:
        if raw.startswith(sig):
            return raw, 0
    if is_webp_at(raw, 0):
        return raw, 0

    candidates: list[int] = []
    for sig in signatures:
        idx = raw.find(sig)
        if idx > 0:
            candidates.append(idx)
    riff_idx = raw.find(b"RIFF")
    if riff_idx > 0 and is_webp_at(raw, riff_idx):
        candidates.append(riff_idx)
    if not candidates:
        return raw, 0
    strip_len = min(candidates)
    return raw[strip_len:], strip_len


def detect_image_format(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
        return "gif"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    return ""


def convert_with_sips(raw: bytes, src_format: str, dst_format: str) -> bytes | None:
    sips_bin = shutil.which("sips")
    if not sips_bin:
        return None
    src_ext = "jpeg" if src_format == "jpg" else src_format
    dst_ext = "jpeg" if dst_format == "jpg" else dst_format
    if not src_ext or not dst_ext:
        return None
    with tempfile.TemporaryDirectory(prefix="aki-image-provider-") as tmp_dir:
        src_path = Path(tmp_dir) / f"in.{src_ext}"
        dst_path = Path(tmp_dir) / f"out.{dst_ext}"
        src_path.write_bytes(raw)
        proc = subprocess.run(
            [sips_bin, "-s", "format", dst_ext, str(src_path), "--out", str(dst_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if proc.returncode != 0 or not dst_path.exists():
            return None
        return dst_path.read_bytes()


def _save_image_bytes(raw: bytes, output_path: Path, provider: str) -> str:
    normalized, _ = normalize_image_bytes(raw)
    detected_format = detect_image_format(normalized)
    output_ext = output_path.suffix.lower().lstrip(".")
    if output_ext == "jpeg":
        output_ext = "jpg"
    final_raw = normalized
    if detected_format and output_ext and detected_format != output_ext:
        converted = convert_with_sips(normalized, detected_format, output_ext)
        if converted is not None:
            final_raw = converted
            detected_format = output_ext
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(final_raw)
    return detected_format or output_ext or "png"


def render_image_with_provider(
    prompt: str,
    output_path: Path,
    provider: str,
    config: dict[str, Any],
) -> ImageRenderResult:
    if provider == "comfly":
        api_url, headers, payload, timeout = build_comfly_request(prompt, config)
        response = request_json(api_url, headers, payload, timeout, provider="comfly")
        kind, data = extract_comfly_image_payload(response)
        user_agent = "aki-comfly-image-provider"
    elif provider == "openrouter":
        api_url, headers, payload, timeout = build_openrouter_request(prompt, config)
        response = request_json(api_url, headers, payload, timeout, provider="openrouter")
        kind, data = extract_openrouter_image_payload(response)
        user_agent = "aki-openrouter-image-provider"
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    if kind == "b64":
        raw = decode_base64_image_payload(data)
    else:
        raw = download_image(data, timeout, user_agent, provider)
    image_format = _save_image_bytes(raw, output_path, provider)
    return ImageRenderResult(output_path=output_path, provider_used=provider, image_format=image_format)


class ImageRouter:
    def __init__(self, policy: str = "auto", configs: dict[str, dict[str, Any]] | None = None) -> None:
        if policy not in {"auto", "comfly", "openrouter"}:
            raise ValueError(f"Unsupported image provider policy: {policy}")
        self.policy = policy
        self.configs = configs or load_provider_configs()
        self.active_provider: str | None = None

    def _has_provider(self, provider: str) -> bool:
        return provider in self.configs

    def current_provider(self) -> str:
        if self.policy in {"comfly", "openrouter"}:
            if not self._has_provider(self.policy):
                raise ImageProviderError(
                    provider=self.policy,
                    category="config",
                    message=f"Missing {self.policy} config.",
                    recoverable=False,
                )
            return self.policy
        if self.active_provider and self._has_provider(self.active_provider):
            return self.active_provider
        if self._has_provider("comfly"):
            return "comfly"
        if self._has_provider("openrouter"):
            return "openrouter"
        raise ImageProviderError(
            provider="router",
            category="config",
            message="No image provider configured. Set Comfly or OpenRouter credentials first.",
            recoverable=False,
        )

    def _cleanup_outputs(self, requests: Iterable[ImageRenderRequest]) -> None:
        for request in requests:
            request.output_path.unlink(missing_ok=True)

    def _render_with_provider(self, provider: str, requests: list[ImageRenderRequest]) -> ImageBatchResult:
        if not self._has_provider(provider):
            raise ImageProviderError(
                provider=provider,
                category="config",
                message=f"Missing {provider} config.",
                recoverable=False,
            )
        config = self.configs[provider]
        rendered: list[ImageRenderResult] = []
        for request in requests:
            try:
                rendered.append(render_image_with_provider(request.prompt, request.output_path, provider, config))
            except ImageProviderError as exc:
                exc.billed_images += len(rendered)
                raise
        self.active_provider = provider
        return ImageBatchResult(
            provider_used=provider,
            fallback_triggered=False,
            rendered_images=rendered,
            provider_billed_images={provider: len(rendered)},
        )

    def render_batch(self, requests: Iterable[ImageRenderRequest]) -> ImageBatchResult:
        batch = list(requests)
        if not batch:
            provider = self.current_provider()
            return ImageBatchResult(
                provider_used=provider,
                fallback_triggered=False,
                rendered_images=[],
                provider_billed_images={},
            )

        provider = self.current_provider()
        try:
            return self._render_with_provider(provider, batch)
        except ImageProviderError as exc:
            if self.policy != "auto" or provider != "comfly" or not exc.recoverable or not self._has_provider("openrouter"):
                raise
            self._cleanup_outputs(batch)
            result = self._render_with_provider("openrouter", batch)
            provider_billed_images = dict(result.provider_billed_images)
            if exc.billed_images:
                provider_billed_images["comfly"] = provider_billed_images.get("comfly", 0) + exc.billed_images
            return ImageBatchResult(
                provider_used=result.provider_used,
                fallback_triggered=True,
                rendered_images=result.rendered_images,
                provider_billed_images=provider_billed_images,
            )


def build_image_router(policy: str = "auto", configs: dict[str, dict[str, Any]] | None = None) -> ImageRouter:
    return ImageRouter(policy=policy, configs=configs)
