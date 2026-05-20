from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from services.render_service import build_render_command


def filter_complex(cmd: list[str]) -> str:
    return cmd[cmd.index("-filter_complex") + 1]


class RenderServiceTests(unittest.TestCase):
    def test_contain_fit_uses_scale_and_pad_for_portrait(self) -> None:
        cmd = build_render_command(
            Path("input.mp4"),
            Path("voice.mp3"),
            Path("out.mp4"),
            {"fit_mode": "contain", "output_width": 1080, "output_height": 1920, "use_nvenc": False},
        )

        filters = filter_complex(cmd)
        self.assertIn("scale=1080:1920:force_original_aspect_ratio=decrease", filters)
        self.assertIn("pad=1080:1920", filters)
        self.assertIn("libx264", cmd)

    def test_cover_and_crop_use_scale_increase_and_crop(self) -> None:
        for fit_mode in ("cover", "crop"):
            cmd = build_render_command(
                Path("input.mp4"),
                Path("voice.mp3"),
                Path("out.mp4"),
                {"fit_mode": fit_mode, "aspect_ratio": "16:9"},
            )

            filters = filter_complex(cmd)
            self.assertIn("scale=1920:1080:force_original_aspect_ratio=increase", filters)
            self.assertIn("crop=1920:1080", filters)

    def test_blur_background_uses_gblur_and_overlay(self) -> None:
        cmd = build_render_command(
            Path("input.mp4"),
            Path("voice.mp3"),
            Path("out.mp4"),
            {"fit_mode": "blur_bg", "blur_strength": 18, "aspect_ratio": "1:1"},
        )

        filters = filter_complex(cmd)
        self.assertIn("gblur=sigma=18", filters)
        self.assertIn("overlay=(W-w)/2:(H-h)/2", filters)

    def test_audio_mix_supports_original_tts_and_music_volumes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            music = Path(temp) / "music.mp3"
            music.write_bytes(b"fake")

            cmd = build_render_command(
                Path("input.mp4"),
                Path("voice.mp3"),
                Path("out.mp4"),
                {
                    "fit_mode": "contain",
                    "music_path": str(music),
                    "keep_original_audio": True,
                    "original_audio_volume": 0.25,
                    "tts_audio_volume": 1.5,
                    "music_volume": 0.05,
                },
            )

        filters = filter_complex(cmd)
        self.assertIn("[0:a]volume=0.25[aorig]", filters)
        self.assertIn("[1:a]volume=1.5[atts]", filters)
        self.assertIn("volume=0.05[amusic]", filters)
        self.assertIn("amix=inputs=3", filters)

    def test_subtitles_and_logo_overlay_are_added_when_files_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            sub = Path(temp) / "subs.srt"
            logo = Path(temp) / "logo.png"
            sub.write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n", encoding="utf-8")
            logo.write_bytes(b"fake")

            cmd = build_render_command(
                Path("input.mp4"),
                Path("voice.mp3"),
                Path("out.mp4"),
                {
                    "fit_mode": "contain",
                    "subtitle_path": str(sub),
                    "logo_path": str(logo),
                    "logo_width": 180,
                    "logo_opacity": 0.5,
                },
            )

        filters = filter_complex(cmd)
        self.assertIn("subtitles=", filters)
        self.assertIn("scale=180:-1", filters)
        self.assertIn("colorchannelmixer=aa=0.5", filters)


if __name__ == "__main__":
    unittest.main()
