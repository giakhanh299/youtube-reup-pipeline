from __future__ import annotations

from pathlib import Path
import unittest

from processors.sheet_client import SheetConfig
from repositories.sheet_repository import SheetRepository


class FakeUploadSheet:
    def __init__(self, headers=None):
        self.updated = None
        self.appended = None
        self.headers = headers or ["video_path", "upload_status", "channel_id", "youtube_token_path"]

    def rows_with_numbers(self, worksheet_name: str):
        return [(2, {"video_path": "video.mp4"})]

    def row_values(self, row_number: int):
        return self.headers if row_number == 1 else []

    def get_all_values(self):
        return [self.headers]

    def update_upload_result(self, *args, **kwargs):
        self.updated = (args, kwargs)

    def update_render_result(self, *args, **kwargs):
        self.render_updated = (args, kwargs)

    def append_row(self, values, value_input_option=None):
        self.appended = {"values": values, "value_input_option": value_input_option}

    def append_row_by_headers(self, worksheet_name: str, row_data: dict):
        values = [row_data.get(header, "") for header in self.headers]
        self.append_row(values, value_input_option="USER_ENTERED")
        return 2


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

    def test_render_sheet_rows_and_updates_delegate_to_sheet_client(self) -> None:
        fake_sheet = FakeUploadSheet()
        repository = SheetRepository(fake_sheet, self.root)

        rows = repository.load_render_jobs("Douyin Render")
        repository.update_render_result(
            "Douyin Render",
            2,
            "ready",
            audio_path="audio.m4a",
            rendered_video_path="out.mp4",
            render_error="",
        )

        self.assertEqual(rows, [(2, {"video_path": "video.mp4"})])
        self.assertEqual(fake_sheet.render_updated[0][:3], ("Douyin Render", 2, "ready"))
        self.assertEqual(fake_sheet.render_updated[1]["rendered_video_path"], "out.mp4")

    def test_load_upload_channel_configs_returns_enabled_configs_only(self) -> None:
        class FakeChannelSheet:
            def map_by(self, worksheet_name, key_col):
                return {
                    "main": {
                        "channel_key": "main",
                        "enabled": "TRUE",
                        "default_privacyStatus": "private",
                        "default_categoryId": "22",
                    },
                    "disabled": {"channel_key": "disabled", "enabled": "FALSE"},
                }

        repository = SheetRepository(FakeChannelSheet(), self.root)

        configs = repository.load_upload_channel_configs("Channel Config")

        self.assertIn("main", configs)
        self.assertNotIn("disabled", configs)
        self.assertEqual(configs["main"]["default_privacyStatus"], "private")

    def test_append_row_by_headers_writes_only_existing_columns(self) -> None:
        fake_sheet = FakeUploadSheet()
        repository = SheetRepository(fake_sheet, self.root)

        row_number = repository.append_row_by_headers(
            "YouTube Upload Queue",
            {
                "video_path": "runtime/output/channel_001/video.mp4",
                "upload_status": "pending",
                "channel_id": "channel_001",
                "channel_key": "channel_001",
                "title": "Title",
                "description": "Desc",
                "tags": "a,b",
                "privacyStatus": "private",
                "categoryId": "22",
                "youtube_token_path": "secrets/token.pickle",
                "missing_optional": "ignore",
            },
        )

        self.assertEqual(row_number, 2)
        self.assertEqual(
            fake_sheet.appended["values"],
            ["runtime/output/channel_001/video.mp4", "pending", "channel_001", "secrets/token.pickle"],
        )
        self.assertEqual(fake_sheet.appended["value_input_option"], "USER_ENTERED")

    def test_append_row_by_headers_ignores_missing_optional_columns(self) -> None:
        fake_sheet = FakeUploadSheet(headers=["video_path", "upload_status"])
        repository = SheetRepository(fake_sheet, self.root)

        row_number = repository.append_row_by_headers(
            "YouTube Upload Queue",
            {
                "video_path": "runtime/output/channel_001/video.mp4",
                "upload_status": "pending",
                "channel_id": "channel_001",
                "youtube_token_path": "secrets/token.pickle",
                "title": "Title",
            },
        )

        self.assertEqual(row_number, 2)
        self.assertEqual(
            fake_sheet.appended["values"],
            ["runtime/output/channel_001/video.mp4", "pending"],
        )


if __name__ == "__main__":
    unittest.main()
