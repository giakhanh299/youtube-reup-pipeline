from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from services.text_service import TextService


class TextServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TextService()

    def test_find_for_video_prefers_vi_subtitle(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            video = folder / "clip.mp4"
            video.write_text("", encoding="utf-8")
            fallback = folder / "clip.srt"
            preferred = folder / "clip_vi.srt"
            fallback.write_text("fallback", encoding="utf-8")
            preferred.write_text("preferred", encoding="utf-8")

            found = self.service.find_for_video(video, folder, ["_vi.srt", ".srt", ".txt"])

        self.assertEqual(found, preferred)

    def test_to_plain_text_removes_srt_timing_and_sequence_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            subtitle = Path(temp) / "clip.srt"
            subtitle.write_text(
                "1\n00:00:00,000 --> 00:00:02,000\nHello\n\n2\n00:00:02,000 --> 00:00:04,000\nWorld\n",
                encoding="utf-8",
            )

            text = self.service.to_plain_text(subtitle)

        self.assertEqual(text, "Hello World")

    def test_to_plain_text_collapses_txt_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            text_file = Path(temp) / "clip.txt"
            text_file.write_text("Hello\n\n   World", encoding="utf-8")

            text = self.service.to_plain_text(text_file)

        self.assertEqual(text, "Hello World")


if __name__ == "__main__":
    unittest.main()
