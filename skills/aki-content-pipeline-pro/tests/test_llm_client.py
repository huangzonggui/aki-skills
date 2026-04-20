from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from urllib.error import URLError
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import llm_client  # noqa: E402


class LlmClientFallbackTests(unittest.TestCase):
    def test_resolve_config_prefers_ai_keys_env_path_override(self) -> None:
        with self.subTest("env override"):
            with mock.patch.object(llm_client, "COMFLY_CONFIG", Path("/nonexistent")):
                with mock.patch.object(llm_client, "default_ai_keys_env_path", return_value=Path("/tmp/keys.env")):
                    with mock.patch.object(llm_client, "_parse_env_file", side_effect=[{}, {"COMFLY_API_KEY": "abc"}]):
                        with mock.patch.dict(os.environ, {}, clear=True):
                            cfg = llm_client.resolve_config()

        self.assertEqual(cfg["api_key"], "abc")

    def test_chat_complete_falls_back_to_curl_on_urlopen_error(self) -> None:
        cfg = {
            "api_key": "test-key",
            "api_url": "https://example.invalid/v1/chat/completions",
            "model": "gemini-2.5-flash",
        }
        curl_payload = (
            '{"choices":[{"message":{"content":"# 标题\\n\\n正文"}}]}'
        )

        with mock.patch.object(llm_client, "resolve_config", return_value=cfg):
            with mock.patch.object(llm_client, "urlopen", side_effect=URLError("ssl eof")):
                with mock.patch("subprocess.run") as run_mock:
                    run_mock.return_value = mock.Mock(returncode=0, stdout=curl_payload, stderr="")

                    result = llm_client.chat_complete("system", "user", model_override="gemini-2.5-flash")

        self.assertEqual(result, "# 标题\n\n正文")
        run_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
