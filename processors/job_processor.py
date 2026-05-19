from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from logs.structured_logger import NullLogger
from services.render_service import RenderService
from services.text_service import TextService
from services.tts_service import TTSService


def safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in name).strip()


class VideoJobProcessor:
    """Processes one video using existing TTS and render behavior."""

    def __init__(
        self,
        root: Path,
        text_service: TextService | None = None,
        tts_service: TTSService | None = None,
        render_service: RenderService | None = None,
        logger: Any = None,
    ):
        self.root = root
        self.text_service = text_service or TextService()
        self.tts_service = tts_service or TTSService()
        self.render_service = render_service or RenderService()
        self.logger = logger or NullLogger()

    def process_one_video(
        self,
        video: Path,
        text_file: Path,
        channel_id: str,
        channel_cfg: dict,
        voices: dict,
        settings: dict,
    ) -> str:
        temp_dir = self.root / settings.get("temp_dir", "runtime/temp") / channel_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_folder = Path(channel_cfg["output_folder"])
        job_name = safe_name(video.stem)
        voice_file = temp_dir / f"{job_name}_{int(time.time())}.mp3"
        output_file = output_folder / f"{channel_id}_{job_name}.mp4"

        try:
            print(f"> [{channel_id}] {video.name}")
            self.logger.app("job_started", channel_id=channel_id, video=str(video))
            print(f"  -> Text: {text_file.name}")
            text = self.text_service.to_plain_text(text_file)
            if not text:
                raise ValueError("Text empty")
            voice_id = channel_cfg["voice_id"]
            if voice_id not in voices:
                raise KeyError(f"Voice not found in VOICE_CONFIG: {voice_id}")
            voice_cfg = voices[voice_id]
            if not voice_cfg.get("active", True):
                raise ValueError(f"Voice is inactive: {voice_id}")
            print(f"  -> Create voice: {voice_id}")
            self.tts_service.create_voice(text, voice_file, voice_cfg, settings["google_key_dir"])
            print("  -> Render video from Google Sheet config")
            self.logger.render("render_started", channel_id=channel_id, video=str(video), output=str(output_file))
            self.render_service.render_video(video, voice_file, output_file, channel_cfg)
            print(f"  OK: {output_file}")
            self.logger.render("render_finished", channel_id=channel_id, video=str(video), output=str(output_file))
            return str(output_file)
        finally:
            try:
                if voice_file.exists():
                    voice_file.unlink()
            except OSError:
                pass
