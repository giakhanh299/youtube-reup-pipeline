from __future__ import annotations

from pathlib import Path
import shutil
import unittest
import uuid

from services.channel_sheet_registry import ChannelSheetRegistry


class FakeSheet:
    def __init__(self, rows):
        self._rows = rows

    def map_by(self, _worksheet_name, key):
        return {row[key]: row for row in self._rows}


class FakeRepository:
    def __init__(self, rows, root):
        self.sheet = FakeSheet(rows)
        self.root = root

    def resolve_path(self, value):
        path = Path(str(value))
        if path.is_absolute():
            return str(path)
        return str((self.root / path).resolve())


class ChannelSheetRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path.cwd() / "runtime" / "test_channel_registry" / uuid.uuid4().hex
        self.root.mkdir(parents=True, exist_ok=True)
        self.voices_dir = self.root / "voices"
        self.voices_dir.mkdir()
        (self.voices_dir / "cute.wav").write_bytes(b"voice")

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_enabled_channels_are_sheet_controlled_and_resolve_voice(self) -> None:
        rows = [
            {
                "channel_id": "ch1",
                "channel_name": "Channel 1",
                "input_folder": "input/ch1",
                "voice_name": "cute.wav",
                "youtube_oauth_token_json": "tokens/ch1.json",
                "privacyStatus": "",
                "enabled": "TRUE",
                "daily_limit": "2",
                "worker_id": "w1",
                "last_error": "",
            },
            {"channel_id": "ch2", "input_folder": "input/ch2", "enabled": "FALSE"},
        ]
        registry = ChannelSheetRegistry(
            FakeRepository(rows, self.root),
            {"voices_dir": str(self.voices_dir)},
            self.root,
        )

        channels = registry.enabled_channels(max_channels=100)

        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0].channel_id, "ch1")
        self.assertEqual(channels[0].privacy_status, "private")
        self.assertEqual(channels[0].daily_limit, 2)
        self.assertEqual(channels[0].voice_path, str((self.voices_dir / "cute.wav").resolve()))
        self.assertTrue(channels[0].youtube_oauth_token_json.endswith("tokens\\ch1.json") or channels[0].youtube_oauth_token_json.endswith("tokens/ch1.json"))

    def test_missing_input_folder_fails_clearly(self) -> None:
        registry = ChannelSheetRegistry(FakeRepository([{"channel_id": "ch1", "enabled": "TRUE"}], self.root), {}, self.root)

        with self.assertRaisesRegex(ValueError, "input_folder is required"):
            registry.enabled_channels()


if __name__ == "__main__":
    unittest.main()
