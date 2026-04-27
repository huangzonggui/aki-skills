from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import image_provider


PNG_DATA_URL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK3cAAAAASUVORK5CYII="


class LoadProviderConfigsTests(unittest.TestCase):
    def test_load_provider_configs_prefers_keys_env_and_sets_openrouter_defaults(self) -> None:
        config_data = {
            "COMFLY_API_KEY": "config-comfly-key",
            "COMFLY_API_BASE_URL": "https://config.example.com",
            "COMFLY_IMAGE_MODEL": "nano-banana-2-4k",
        }
        keys_data = {
            "COMFLY_API_KEY": "keys-comfly-key",
            "COMFLY_API_BASE_URL": "https://keys.example.com",
            "COMFLY_IMAGE_MODEL": "nano-banana-2-2k",
            "COMFLY_IMAGE_SIZE": "1024x1536",
            "COMFLY_IMAGE_QUALITY": "high",
            "OPENROUTER_API_KEY": "openrouter-key",
        }

        with patch.object(
            image_provider,
            "parse_env_like_file",
            side_effect=lambda path: dict(keys_data)
            if str(path).endswith("keys.env")
            else dict(config_data),
        ):
            configs = image_provider.load_provider_configs()

        self.assertEqual(configs["comfly"]["api_key"], "keys-comfly-key")
        self.assertEqual(configs["comfly"]["base_url"], "https://keys.example.com")
        self.assertEqual(configs["comfly"]["size"], "1024x1536")
        self.assertEqual(configs["comfly"]["quality"], "high")
        self.assertEqual(configs["openrouter"]["api_key"], "openrouter-key")
        self.assertEqual(
            configs["openrouter"]["api_url"],
            "https://openrouter.ai/api/v1/chat/completions",
        )
        self.assertEqual(
            configs["openrouter"]["image_model"],
            "google/gemini-3.1-flash-image-preview",
        )
        self.assertEqual(configs["openrouter"]["image_size"], "2K")


class OpenRouterRequestTests(unittest.TestCase):
    def test_build_comfly_request_includes_optional_size_and_quality(self) -> None:
        config = {
            "base_url": "https://ai.comfly.chat",
            "path": "/v1/images/generations",
            "api_key": "comfly-key",
            "image_model": "gpt-image-2",
            "aspect_ratio": "3:4",
            "image_size": "",
            "size": "1024x1536",
            "quality": "high",
            "image": [],
            "timeout_sec": 120,
            "auth_header": "Authorization",
            "auth_prefix": "Bearer ",
            "accept_language": "zh-CN",
            "extra_body": {},
        }

        api_url, headers, payload, timeout = image_provider.build_comfly_request("draw this", config)

        self.assertEqual(api_url, "https://ai.comfly.chat/v1/images/generations")
        self.assertEqual(headers["Authorization"], "Bearer comfly-key")
        self.assertEqual(payload["model"], "gpt-image-2")
        self.assertEqual(payload["size"], "1024x1536")
        self.assertEqual(payload["quality"], "high")
        self.assertEqual(payload["aspect_ratio"], "3:4")
        self.assertEqual(payload["response_format"], "b64_json")
        self.assertEqual(timeout, 120)

    def test_build_openrouter_request_uses_modalities_and_image_config(self) -> None:
        config = {
            "api_url": "https://openrouter.ai/api/v1/chat/completions",
            "api_key": "openrouter-key",
            "image_model": "google/gemini-3.1-flash-image-preview",
            "aspect_ratio": "3:4",
            "image_size": "4K",
            "timeout_sec": 90,
            "app_name": "",
            "site_url": "",
        }

        api_url, headers, payload, timeout = image_provider.build_openrouter_request("draw this", config)

        self.assertEqual(api_url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer openrouter-key")
        self.assertEqual(payload["model"], "google/gemini-3.1-flash-image-preview")
        self.assertEqual(payload["modalities"], ["image", "text"])
        self.assertEqual(payload["messages"][0]["content"], "draw this")
        self.assertEqual(payload["image_config"]["aspect_ratio"], "3:4")
        self.assertEqual(payload["image_config"]["image_size"], "4K")
        self.assertFalse(payload["stream"])
        self.assertEqual(timeout, 90)


class ImageRouterTests(unittest.TestCase):
    def test_render_single_openrouter_response_writes_png(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.png"
            configs = {
                "openrouter": {
                    "api_url": "https://openrouter.ai/api/v1/chat/completions",
                    "api_key": "openrouter-key",
                    "image_model": "google/gemini-3.1-flash-image-preview",
                    "aspect_ratio": "3:4",
                    "image_size": "2K",
                    "timeout_sec": 90,
                    "app_name": "",
                    "site_url": "",
                }
            }
            router = image_provider.ImageRouter(policy="openrouter", configs=configs)

            with patch.object(
                image_provider,
                "request_json",
                return_value={
                    "choices": [
                        {
                            "message": {
                                "images": [
                                    {
                                        "image_url": {
                                            "url": PNG_DATA_URL,
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                },
            ):
                result = router.render_batch(
                    [image_provider.ImageRenderRequest(prompt="draw this", output_path=output_path)]
                )
            self.assertEqual(result.provider_used, "openrouter")
            self.assertFalse(result.fallback_triggered)
            self.assertEqual(result.rendered_images[0].image_format, "png")
            self.assertTrue(output_path.exists())
            self.assertTrue(output_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_render_request_overrides_aspect_ratio_per_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.png"
            configs = {
                "openrouter": {
                    "api_url": "https://openrouter.ai/api/v1/chat/completions",
                    "api_key": "openrouter-key",
                    "image_model": "google/gemini-3.1-flash-image-preview",
                    "aspect_ratio": "3:4",
                    "image_size": "2K",
                    "timeout_sec": 90,
                    "app_name": "",
                    "site_url": "",
                }
            }
            router = image_provider.ImageRouter(policy="openrouter", configs=configs)
            seen: dict[str, object] = {}

            def fake_render(prompt: str, output_path: Path, provider: str, config: dict[str, object]):
                seen["aspect_ratio"] = config["aspect_ratio"]
                output_path.write_bytes(b"\x89PNG\r\n\x1a\nopenrouter")
                return image_provider.ImageRenderResult(
                    output_path=output_path,
                    provider_used=provider,
                    image_format="png",
                )

            with patch.object(image_provider, "render_image_with_provider", side_effect=fake_render):
                router.render_batch(
                    [
                        image_provider.ImageRenderRequest(
                            prompt="draw this",
                            output_path=output_path,
                            aspect_ratio="9:16",
                            profile="douyin_series_safe_84",
                        )
                    ]
                )

            self.assertEqual(seen["aspect_ratio"], "9:16")

    def test_router_falls_back_from_comfly_to_openrouter_and_clears_partial_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            first = tmp_path / "01.png"
            second = tmp_path / "02.png"
            configs = {
                "comfly": {
                    "base_url": "https://ai.comfly.chat",
                    "path": "/v1/images/generations",
                    "api_key": "comfly-key",
                    "image_model": "nano-banana-2-2k",
                    "aspect_ratio": "3:4",
                    "image_size": "",
                    "image": [],
                    "timeout_sec": 90,
                    "auth_header": "Authorization",
                    "auth_prefix": "Bearer ",
                    "accept_language": "zh-CN",
                    "extra_body": {},
                },
                "openrouter": {
                    "api_url": "https://openrouter.ai/api/v1/chat/completions",
                    "api_key": "openrouter-key",
                    "image_model": "google/gemini-3.1-flash-image-preview",
                    "aspect_ratio": "3:4",
                    "image_size": "2K",
                    "timeout_sec": 90,
                    "app_name": "",
                    "site_url": "",
                },
            }
            router = image_provider.ImageRouter(policy="auto", configs=configs)
            requests = [
                image_provider.ImageRenderRequest(prompt="first", output_path=first),
                image_provider.ImageRenderRequest(prompt="second", output_path=second),
            ]

            comfly_calls = {"count": 0}

            def fake_render(prompt: str, output_path: Path, provider: str, config: dict[str, object]):
                if provider == "comfly":
                    comfly_calls["count"] += 1
                    if comfly_calls["count"] == 1:
                        output_path.write_bytes(b"partial-comfly")
                        return image_provider.ImageRenderResult(
                            output_path=output_path,
                            provider_used="comfly",
                            image_format="png",
                        )
                    raise image_provider.ImageProviderError(
                        provider="comfly",
                        category="transient",
                        message="timeout",
                        recoverable=True,
                    )
                output_path.write_bytes(b"\x89PNG\r\n\x1a\nopenrouter")
                return image_provider.ImageRenderResult(
                    output_path=output_path,
                    provider_used="openrouter",
                    image_format="png",
                )

            with patch.object(image_provider, "render_image_with_provider", side_effect=fake_render):
                result = router.render_batch(requests)
            self.assertEqual(result.provider_used, "openrouter")
            self.assertTrue(result.fallback_triggered)
            self.assertEqual(result.provider_billed_images["comfly"], 1)
            self.assertEqual(result.provider_billed_images["openrouter"], 2)
            self.assertTrue(first.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertTrue(second.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_router_does_not_fallback_on_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.png"
            configs = {
                "comfly": {
                    "base_url": "https://ai.comfly.chat",
                    "path": "/v1/images/generations",
                    "api_key": "comfly-key",
                    "image_model": "nano-banana-2-2k",
                    "aspect_ratio": "3:4",
                    "image_size": "",
                    "image": [],
                    "timeout_sec": 90,
                    "auth_header": "Authorization",
                    "auth_prefix": "Bearer ",
                    "accept_language": "zh-CN",
                    "extra_body": {},
                },
                "openrouter": {
                    "api_url": "https://openrouter.ai/api/v1/chat/completions",
                    "api_key": "openrouter-key",
                    "image_model": "google/gemini-3.1-flash-image-preview",
                    "aspect_ratio": "3:4",
                    "image_size": "2K",
                    "timeout_sec": 90,
                    "app_name": "",
                    "site_url": "",
                },
            }
            router = image_provider.ImageRouter(policy="auto", configs=configs)

            with patch.object(
                image_provider,
                "render_image_with_provider",
                side_effect=image_provider.ImageProviderError(
                    provider="comfly",
                    category="config",
                    message="missing model",
                    recoverable=False,
                ),
            ):
                with self.assertRaises(image_provider.ImageProviderError):
                    router.render_batch(
                        [image_provider.ImageRenderRequest(prompt="draw this", output_path=output_path)]
                    )
