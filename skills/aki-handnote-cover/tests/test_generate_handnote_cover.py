from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import generate_handnote_cover  # noqa: E402


class GenerateHandnoteCoverTests(unittest.TestCase):
    def test_clean_article_strips_media_promo_and_bare_urls(self) -> None:
        raw = """# DeepSeek V4 发布

核心信息保留。

APPSO 马上会带来更详细的解读，敬请留意。

https://api-docs.deepseek.com/zh-cn/guides/thinking_mode
"""

        cleaned = generate_handnote_cover.clean_article_for_cover(raw)

        self.assertIn("核心信息保留。", cleaned)
        self.assertNotIn("APPSO", cleaned)
        self.assertNotIn("敬请留意", cleaned)
        self.assertNotIn("api-docs.deepseek.com", cleaned)

    def test_allows_nano_banana_4k_aliases(self) -> None:
        self.assertIn(
            "nano-banana-pro-4k",
            generate_handnote_cover.allowed_response_model_aliases("nano-banana-2-4k"),
        )
        self.assertIn(
            "nano-banana-2-4k",
            generate_handnote_cover.allowed_response_model_aliases("nano-banana-pro-4k"),
        )

    def test_request_json_delegates_to_shared_provider_client(self) -> None:
        with mock.patch.object(
            generate_handnote_cover,
            "shared_request_json",
            return_value={"ok": True},
        ) as shared_mock:
            result = generate_handnote_cover.request_json(
                "https://example.com/api",
                {"Authorization": "Bearer test"},
                {"hello": "world"},
                30,
            )

        self.assertEqual(result, {"ok": True})
        shared_mock.assert_called_once()

    def test_main_defaults_to_prompt_only_without_paid_api_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            article = tmp_dir / "article.md"
            prompt_out = tmp_dir / "prompt.md"
            output = tmp_dir / "cover.png"
            article.write_text("# 标题\n\n正文内容。", encoding="utf-8")

            argv = [
                "generate_handnote_cover.py",
                "--article",
                str(article),
                "--prompt-out",
                str(prompt_out),
                "--output",
                str(output),
            ]
            with mock.patch.object(generate_handnote_cover.sys, "argv", argv):
                with mock.patch.object(generate_handnote_cover, "build_image_router") as router_mock:
                    exit_code = generate_handnote_cover.main()

            self.assertEqual(exit_code, 0)
            self.assertTrue(prompt_out.exists())
            self.assertFalse(output.exists())
            router_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
