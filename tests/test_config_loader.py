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


if __name__ == "__main__":
    unittest.main()
