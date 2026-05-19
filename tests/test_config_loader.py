from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from configs.config_loader import ConfigLoader, apply_env_overrides, load_env_file


class ConfigLoaderTests(unittest.TestCase):
    def test_apply_env_overrides_coerces_existing_value_types(self) -> None:
        settings = {
            "process_queue_only": False,
            "retry_max_attempts": 3,
            "retry_base_delay": 1.0,
            "video_exts": [".mp4"],
            "spreadsheet_id": "old",
        }
        env = {
            "YT_PROCESS_QUEUE_ONLY": "true",
            "YT_RETRY_MAX_ATTEMPTS": "5",
            "YT_RETRY_BASE_DELAY": "0.25",
            "YT_VIDEO_EXTS": ".mp4,.mkv",
            "YT_SPREADSHEET_ID": "new",
        }

        merged = apply_env_overrides(settings, env)

        self.assertTrue(merged["process_queue_only"])
        self.assertEqual(merged["retry_max_attempts"], 5)
        self.assertEqual(merged["retry_base_delay"], 0.25)
        self.assertEqual(merged["video_exts"], [".mp4", ".mkv"])
        self.assertEqual(merged["spreadsheet_id"], "new")

    def test_load_env_file_ignores_comments_and_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env_path = Path(temp) / ".env"
            env_path.write_text("\n# comment\nYT_SPREADSHEET_ID='abc'\n", encoding="utf-8")

            values = load_env_file(env_path)

        self.assertEqual(values, {"YT_SPREADSHEET_ID": "abc"})

    def test_config_loader_reads_json_and_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "configs").mkdir()
            (root / "configs" / "settings.json").write_text(
                '{"spreadsheet_id": "old", "process_queue_only": false}',
                encoding="utf-8",
            )
            (root / ".env").write_text("APP_SPREADSHEET_ID=new\nAPP_PROCESS_QUEUE_ONLY=true\n", encoding="utf-8")

            settings = ConfigLoader(root, env_prefix="APP_").load_settings()

        self.assertEqual(settings["spreadsheet_id"], "new")
        self.assertTrue(settings["process_queue_only"])

    def test_legacy_youtube_env_aliases_are_supported(self) -> None:
        settings = {
            "youtube_oauth_token_json": "runtime/state/youtube/token.json",
            "youtube_default_privacy": "private",
            "youtube_default_category_id": "22",
        }
        env = {
            "YT_YOUTUBE_TOKEN_PICKLE_PATH": "./secrets/youtube_token.pickle",
            "YOUTUBE_DEFAULT_PRIVACY": "unlisted",
            "YOUTUBE_CATEGORY_ID": "24",
        }

        merged = apply_env_overrides(settings, env)

        self.assertEqual(merged["youtube_oauth_token_json"], "./secrets/youtube_token.pickle")
        self.assertEqual(merged["youtube_default_privacy"], "unlisted")
        self.assertEqual(merged["youtube_default_category_id"], "24")

    def test_canonical_youtube_token_env_wins_over_legacy_alias(self) -> None:
        settings = {"youtube_oauth_token_json": "runtime/state/youtube/token.json"}
        env = {
            "YT_YOUTUBE_OAUTH_TOKEN_JSON": "./secrets/token.json",
            "YT_YOUTUBE_TOKEN_PICKLE_PATH": "./secrets/youtube_token.pickle",
        }

        merged = apply_env_overrides(settings, env)

        self.assertEqual(merged["youtube_oauth_token_json"], "./secrets/token.json")


if __name__ == "__main__":
    unittest.main()
