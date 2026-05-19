from __future__ import annotations

from pathlib import Path
import unittest

from processors.sheet_client import SheetConfig
from repositories.sheet_repository import SheetRepository


class FakeUploadSheet:
    def __init__(self):
        self.updated = None

    def rows_with_numbers(self, worksheet_name: str):
        return [(2, {"video_path": "video.mp4"})]

    def update_upload_result(self, *args, **kwargs):
        self.updated = (args, kwargs)


class SheetRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.repository = SheetRepository(SheetConfig("", ""), self.root)

    def test_resolve_path_keeps_empty_value_empty(self) -> None:
        self.assertEqual(self.repository.resolve_path(""), "")

    def test_resolve_path_expands_relative_value_from_project_root(self) -> None:
        expected = str((self.root / "assets" / "logo.png").resolve())
        self.assertEqual(self.repository.resolve_path("assets/logo.png"), expected)

    def test_normalize_channel_converts_basic_types(self) -> None:
        channel = self.repository.normalize_channel(
            {
                "enabled": "FALSE",
                "blur_strength": "32",
                "speed": "1,25",
                "logo_opacity": "0.5",
                "music_volume": "0.08",
            }
        )

        self.assertFalse(channel["enabled"])
        self.assertEqual(channel["blur_strength"], 32)
        self.assertEqual(channel["speed"], 1.25)
        self.assertEqual(channel["logo_opacity"], 0.5)
        self.assertEqual(channel["music_volume"], 0.08)

    def test_merge_pack_into_channel_applies_preset_music_and_overlay(self) -> None:
        channel = self.repository.normalize_channel(
            {
                "music_pack_id": "music_1",
                "overlay_pack_id": "overlay_1",
                "render_preset_id": "preset_1",
            }
        )

        merged = self.repository.merge_pack_into_channel(
            channel,
            {"music_1": {"music_path": "music/bg.mp3", "music_volume": "0.11"}},
            {
                "overlay_1": {
                    "logo_path": "logos/a.png",
                    "logo_opacity": "0.2",
                    "logo_x": "W-w-30",
                    "logo_y": "40",
                    "background_blur": "TRUE",
                    "blur_strength": "30",
                }
            },
            {"preset_1": {"speed": "1.02", "use_nvenc": "FALSE"}},
        )

        self.assertEqual(merged["music_volume"], 0.11)
        self.assertEqual(merged["logo_opacity"], 0.2)
        self.assertEqual(merged["logo_x"], "W-w-30")
        self.assertEqual(merged["speed"], 1.02)
        self.assertFalse(merged["use_nvenc"])
        self.assertEqual(merged["blur_strength"], 30)

    def test_upload_sheet_rows_and_updates_delegate_to_sheet_client(self) -> None:
        fake_sheet = FakeUploadSheet()
        repository = SheetRepository(fake_sheet, self.root)

        rows = repository.load_upload_jobs("Video đã edit")
        repository.update_upload_result(
            "Video đã edit",
            2,
            "uploaded",
            youtube_video_id="yt123",
            upload_error="",
            upload_time="2026-05-20T00:00:00+00:00",
        )

        self.assertEqual(rows, [(2, {"video_path": "video.mp4"})])
        self.assertEqual(fake_sheet.updated[0][:3], ("Video đã edit", 2, "uploaded"))
        self.assertEqual(fake_sheet.updated[1]["youtube_video_id"], "yt123")


if __name__ == "__main__":
    unittest.main()
