from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from base64 import b64decode
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "render_images.py"
SPEC = importlib.util.spec_from_file_location("render_images", MODULE_PATH)
render_images = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(render_images)


PNG_BYTES = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK3cAAAAASUVORK5CYII="
)


class _FakeRouter:
    def __init__(self, provider_used: str, fallback_triggered: bool) -> None:
        self.provider_used = provider_used
        self.fallback_triggered = fallback_triggered
        self.last_requests = []

    def render_batch(self, requests):
        self.last_requests = list(requests)
        rendered = []
        for request in requests:
            request.output_path.parent.mkdir(parents=True, exist_ok=True)
            request.output_path.write_bytes(PNG_BYTES)
            rendered.append(
                render_images.ImageRenderResult(
                    output_path=request.output_path,
                    provider_used=self.provider_used,
                    image_format="png",
                )
            )
        return render_images.ImageBatchResult(
            provider_used=self.provider_used,
            fallback_triggered=self.fallback_triggered,
            rendered_images=rendered,
            provider_billed_images={self.provider_used: len(rendered)},
        )


def test_render_platform_images_uses_batch_router_and_returns_provider_metadata() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        topic_root = Path(tmpdir)
        layout = render_images.resolve_layout(topic_root)
        layout.ensure_structure()
        (layout.prompts_dir / "cover_prompt.md").write_text("# Cover\n\nprompt", encoding="utf-8")
        (layout.prompts_dir / "series_01_prompt.md").write_text("# Series 1\n\nprompt", encoding="utf-8")
        router = _FakeRouter(provider_used="openrouter", fallback_triggered=True)

        result = render_images._render_platform_images(layout, "wechat", router)

        assert result["provider_used"] == "openrouter"
        assert result["fallback_triggered"] is True
        assert result["original_png"] == 2
        assert result["jpg"] == 2
        assert len(router.last_requests) == 2
        assert all(request.aspect_ratio == "" for request in router.last_requests)
        assert all(request.profile == "" for request in router.last_requests)
        assert (layout.platform_images_dir("wechat") / "cover_01.jpg").exists()
        assert (layout.platform_original_images_dir("wechat") / "series_01.png").exists()


def test_render_platform_images_passes_douyin_profile_to_image_provider() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        topic_root = Path(tmpdir)
        layout = render_images.resolve_layout(topic_root)
        layout.ensure_structure()
        (layout.prompts_dir / "cover_prompt.md").write_text("# Cover\n\nprompt", encoding="utf-8")
        router = _FakeRouter(provider_used="openrouter", fallback_triggered=False)

        result = render_images._render_platform_images(layout, "douyin", router)

        assert router.last_requests[0].aspect_ratio == "9:16"
        assert router.last_requests[0].profile == "douyin_series_safe_84"
        assert "84% safe content area" in router.last_requests[0].prompt
        assert (layout.platform_images_dir("douyin") / "cover_01.jpg").exists()
        assert result["render_profile"]["name"] == "douyin_series_safe_84"
        assert result["render_profile"]["aspect_ratio"] == "9:16"


def test_write_cost_summary_includes_provider_metadata() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        topic_root = Path(tmpdir)
        layout = render_images.resolve_layout(topic_root)
        layout.ensure_structure()
        originals = layout.platform_original_images_dir("wechat")
        publish = layout.platform_images_dir("wechat")
        (originals / "cover_01.png").write_bytes(b"\x89PNG\r\n\x1a\npng")
        (publish / "cover_01.jpg").write_bytes(b"\xff\xd8\xffjpg")

        _, cost_json, summary = render_images._write_cost_summary(
            layout,
            "prod",
            0.6,
            ["wechat"],
            {
                "wechat": {
                    "provider_used": "openrouter",
                    "fallback_triggered": True,
                    "provider_billed_images": {"openrouter": 1},
                }
            },
        )

        payload = json.loads(cost_json.read_text(encoding="utf-8"))
        assert summary["counts"]["wechat"]["provider_used"] == "openrouter"
        assert payload["counts"]["wechat"]["fallback_triggered"] is True
        assert payload["provider_totals"]["openrouter"] == 1
