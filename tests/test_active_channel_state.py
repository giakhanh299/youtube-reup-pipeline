from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from services.active_channel_state import ActiveChannelStateStore
from services.channel_sheet_registry import ChannelSheetConfig


class ActiveChannelStateTests(unittest.TestCase):
    def setUp(self) -> None:
        base = Path.home() / ".codex" / "memories"
        if not base.exists():
            base = Path(tempfile.gettempdir())
        self.root = base / f"test_active_channel_{uuid.uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _channel(self, channel_id: str = "ch_a", token: str = "tokens/a.pickle") -> ChannelSheetConfig:
        return ChannelSheetConfig(
            channel_id=channel_id,
            channel_name="Channel A",
            input_folder="legacy/input",
            output_folder="legacy/output",
            voice_id="voice_1",
            voice_name="voice.wav",
            voice_path="runtime/voices/voice.wav",
            youtube_oauth_token_json=token,
            enabled=True,
            source_folder_id="drive_folder_a",
        )

    def test_select_writes_active_state_and_cleans_shared_folders(self) -> None:
        settings = {
            "shared_input_dir": str(self.root / "runtime" / "input"),
            "shared_processing_dir": str(self.root / "runtime" / "processing"),
            "shared_output_dir": str(self.root / "runtime" / "output"),
            "active_channel_lock_path": str(self.root / "runtime" / "state" / "active_channel.lock"),
            "active_channel_state_path": str(self.root / "runtime" / "state" / "active_channel.json"),
        }
        for folder_name in ("input", "processing", "output"):
            folder = self.root / "runtime" / folder_name
            folder.mkdir(parents=True)
            (folder / "stale.txt").write_text("stale", encoding="utf-8")

        store = ActiveChannelStateStore(self.root, settings)
        state = store.select(self._channel(), clean_before_start=True)

        self.assertEqual(state.channel_id, "ch_a")
        self.assertEqual(state.youtube_token_path, "tokens/a.pickle")
        self.assertEqual(state.source_folder_id, "drive_folder_a")
        self.assertEqual(store.load().channel_id, "ch_a")
        self.assertTrue((self.root / "runtime" / "state" / "active_channel.lock").exists())
        self.assertEqual(list((self.root / "runtime" / "input").iterdir()), [])
        self.assertEqual(list((self.root / "runtime" / "processing").iterdir()), [])
        self.assertEqual(list((self.root / "runtime" / "output").iterdir()), [])

        store.finish(clean_after_finish=True)
        self.assertFalse((self.root / "runtime" / "state" / "active_channel.lock").exists())
        self.assertFalse((self.root / "runtime" / "state" / "active_channel.json").exists())

    def test_lock_prevents_second_active_channel(self) -> None:
        settings = {
            "active_channel_lock_path": str(self.root / "runtime" / "state" / "active_channel.lock"),
            "active_channel_state_path": str(self.root / "runtime" / "state" / "active_channel.json"),
        }
        first = ActiveChannelStateStore(self.root, settings)
        second = ActiveChannelStateStore(self.root, settings)
        first.select(self._channel("ch_a", "tokens/a.pickle"), clean_before_start=False)

        with self.assertRaisesRegex(RuntimeError, "active channel job lock exists"):
            second.select(self._channel("ch_b", "tokens/b.pickle"), clean_before_start=False)

        first.finish(clean_after_finish=False)


if __name__ == "__main__":
    unittest.main()
