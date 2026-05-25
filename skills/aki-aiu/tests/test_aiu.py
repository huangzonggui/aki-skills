import argparse
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "aiu.py"
SPEC = importlib.util.spec_from_file_location("aiu", SCRIPT)
aiu = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(aiu)


class AiuConfigTests(unittest.TestCase):
    def test_cygces_profile_reads_global_keys_env_and_hermes_key_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "keys.env"
            env_file.write_text(
                "\n".join(
                    [
                        "CYGCES_BASE=https://codex-manager.cygces.com",
                        "CYGCES_USERNAME=aki@example.com",
                        "CYGCES_PASSWORD=fill-me",
                        "CYGCES_HERMES_API_KEY=sk-test",
                        "CYGCES_INTERVAL=45",
                    ]
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(profile="cygces", interval=None)
            with patch.dict(os.environ, {}, clear=True), patch.object(aiu, "AI_KEYS_ENV", env_file), patch.object(aiu, "FALLBACK_AI_KEYS_ENV", env_file):
                config = aiu.resolve_config(args)

        self.assertEqual(config.profile, "cygces")
        self.assertEqual(config.base, "https://codex-manager.cygces.com")
        self.assertEqual(config.username, "aki@example.com")
        self.assertEqual(config.password, "fill-me")
        self.assertEqual(config.api_key, "sk-test")
        self.assertEqual(config.interval, 45)
        self.assertEqual(config.api_style, "sub2api")

    def test_skill_local_env_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            script_dir = Path(tmp) / "skill" / "scripts"
            local_env = script_dir.parent / ".env"
            global_keys = Path(tmp) / "keys.env"
            script_dir.mkdir(parents=True)
            local_env.write_text(
                "\n".join(
                    [
                        "DSHUB_BASE=https://local.example.com",
                        "DSHUB_USERNAME=local-user",
                        "DSHUB_PASSWORD=local-pass",
                    ]
                ),
                encoding="utf-8",
            )
            global_keys.write_text(
                "\n".join(
                    [
                        "DSHUB_BASE=https://global.example.com",
                        "DSHUB_USERNAME=global-user",
                        "DSHUB_PASSWORD=global-pass",
                    ]
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(profile="dshub", interval=None)
            with patch.dict(os.environ, {}, clear=True), patch.object(aiu, "__file__", str(script_dir / "aiu.py")), patch.object(aiu, "AI_KEYS_ENV", global_keys), patch.object(aiu, "FALLBACK_AI_KEYS_ENV", global_keys):
                config = aiu.resolve_config(args)

        self.assertEqual(config.base, "https://global.example.com")
        self.assertEqual(config.username, "global-user")
        self.assertEqual(config.password, "global-pass")

    def test_fallback_linux_keys_env_is_loaded_when_mac_path_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_mac_keys = Path(tmp) / "missing" / "keys.env"
            fallback_keys = Path(tmp) / "home" / ".config" / "ai" / "keys.env"
            fallback_keys.parent.mkdir(parents=True)
            fallback_keys.write_text(
                "\n".join(
                    [
                        "DSHUB_BASE=https://linux.example.com",
                        "DSHUB_USERNAME=linux-user",
                        "DSHUB_PASSWORD=linux-pass",
                    ]
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(profile="dshub", interval=None)
            with patch.dict(os.environ, {}, clear=True), patch.object(aiu, "AI_KEYS_ENV", missing_mac_keys), patch.object(aiu, "FALLBACK_AI_KEYS_ENV", fallback_keys):
                config = aiu.resolve_config(args)

        self.assertEqual(config.base, "https://linux.example.com")
        self.assertEqual(config.username, "linux-user")
        self.assertEqual(config.password, "linux-pass")

    def test_known_profiles_document_built_in_relays(self):
        profiles = aiu.known_profiles()
        self.assertIn("dshub", profiles)
        self.assertIn("cygces", profiles)
        self.assertEqual(profiles["cygces"]["api_style"], "sub2api")
        self.assertEqual(aiu.normalize_profile("token-wave"), "dshub")
        self.assertEqual(aiu.normalize_profile("cyg"), "cygces")
        self.assertEqual(aiu.normalize_profile("sub2api"), "cygces")

    def test_resolve_profiles_defaults_to_both_relays(self):
        self.assertEqual(aiu.resolve_profiles(None), ["dshub", "cygces"])
        self.assertEqual(aiu.resolve_profiles(""), ["dshub", "cygces"])
        self.assertEqual(aiu.resolve_profiles("all"), ["dshub", "cygces"])
        self.assertEqual(aiu.resolve_profiles("both"), ["dshub", "cygces"])

    def test_resolve_profiles_accepts_single_alias_and_multi_profile(self):
        self.assertEqual(aiu.resolve_profiles("cyg"), ["cygces"])
        self.assertEqual(aiu.resolve_profiles("token-wave"), ["dshub"])
        self.assertEqual(aiu.resolve_profiles("dshub,cyg"), ["dshub", "cygces"])
        self.assertEqual(aiu.resolve_profiles("cyg+dshub"), ["cygces", "dshub"])

    def test_default_cli_profile_list_ignores_aiu_profile_env(self):
        with patch.dict(os.environ, {"AIU_PROFILE": "cygces"}, clear=True):
            self.assertEqual(aiu.resolve_profiles(None), ["dshub", "cygces"])

    def test_resolve_config_can_target_each_default_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "keys.env"
            env_file.write_text(
                "\n".join(
                    [
                        "DSHUB_BASE=https://api.dshub.top",
                        "DSHUB_API_STYLE=new-api",
                        "DSHUB_API_KEY=sk-dshub-test",
                        "CYGCES_BASE=https://codex-manager.cygces.com",
                        "CYGCES_API_STYLE=sub2api",
                        "CYGCES_USERNAME=aki@example.com",
                        "CYGCES_PASSWORD=fill-me",
                    ]
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(profile=None, interval=None)
            with patch.dict(os.environ, {}, clear=True), patch.object(aiu, "AI_KEYS_ENV", env_file), patch.object(aiu, "FALLBACK_AI_KEYS_ENV", env_file):
                configs = [aiu.resolve_config(args, profile) for profile in aiu.resolve_profiles("both")]

        self.assertEqual([config.profile for config in configs], ["dshub", "cygces"])
        self.assertEqual(configs[0].api_style, "new-api")
        self.assertEqual(configs[0].api_key, "sk-dshub-test")
        self.assertEqual(configs[1].api_style, "sub2api")
        self.assertEqual(configs[1].username, "aki@example.com")


class AiuSummaryTests(unittest.TestCase):
    def test_summary_includes_new_api_token_usage(self):
        summary = aiu.build_summary(
            {
                "username": "aki",
                "display_name": "Aki",
                "group": "default",
                "quota": 500_000,
                "used_quota": 250_000,
                "request_count": 3,
            },
            {"subscriptions": []},
            token_usage={
                "name": "Hermes",
                "total_granted": 2_500_000,
                "total_used": 1_000_000,
                "total_available": 1_500_000,
                "unlimited_quota": False,
                "model_limits_enabled": True,
                "model_limits": {"gpt-5.5": True},
                "expires_at": 0,
            },
            source={"profile": "cygces", "base": "https://codex-manager.cygces.com"},
        )

        token = summary["token_usage"]
        self.assertEqual(token["name"], "Hermes")
        self.assertEqual(token["total_granted_usd"], 5.0)
        self.assertEqual(token["total_used_usd"], 2.0)
        self.assertEqual(token["total_available_usd"], 3.0)
        self.assertEqual(token["expires_at_text"], "永不过期")
        self.assertEqual(token["models"], ["gpt-5.5"])
        self.assertEqual(summary["source"]["profile"], "cygces")

    def test_sub2api_summary_includes_key_quota_and_usage(self):
        summary = aiu.build_sub2api_summary(
            user={"email": "aki@example.com", "display_name": "Aki"},
            keys_data={
                "items": [
                    {
                        "id": 16,
                        "name": "Hermes",
                        "status": "active",
                        "quota": 100.0,
                        "quota_used": 31.25,
                        "expires_at": None,
                        "group": {"name": "codex", "platform": "openai"},
                    }
                ],
                "total": 1,
            },
            usage_data={"stats": {"16": {"today_actual_cost": 2.5, "total_actual_cost": 31.25}}},
            source={"profile": "cygces", "base": "https://codex-manager.cygces.com"},
        )

        key = summary["api_keys"][0]
        self.assertEqual(key["name"], "Hermes")
        self.assertEqual(key["quota_usd"], 100.0)
        self.assertEqual(key["used_usd"], 31.25)
        self.assertEqual(key["remaining_usd"], 68.75)
        self.assertEqual(key["today_used_usd"], 2.5)
        self.assertEqual(key["expires_at_text"], "永不过期")


if __name__ == "__main__":
    unittest.main()
