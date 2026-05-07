from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import generate_handnote_series as ghs


class RequestJsonTests(unittest.TestCase):
    def test_request_json_delegates_to_shared_provider_client(self) -> None:
        payload = {"ok": True}
        expected = {"data": [{"b64_json": "abc"}]}

        with patch.object(ghs, "shared_request_json", return_value=expected) as shared_mock:
            result = ghs.request_json(
                "https://example.com/v1/images/generations",
                {"Authorization": "Bearer test"},
                payload,
                timeout=1,
            )

        self.assertEqual(result, expected)
        shared_mock.assert_called_once()


class LoadImageApiSettingsTests(unittest.TestCase):
    def test_load_image_api_settings_delegates_to_shared_provider_config(self) -> None:
        expected = {
            "api_key": "keys-key",
            "base_url": "https://keys.example.com",
            "image_model": "nano-banana-2-4k",
        }

        with patch.object(ghs, "shared_load_comfly_settings", return_value=expected) as shared_mock:
            settings = ghs.load_image_api_settings(Path("/tmp/unused"))

        self.assertEqual(settings, expected)
        shared_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
