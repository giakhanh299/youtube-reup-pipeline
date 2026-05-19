from __future__ import annotations

from pathlib import Path
from typing import Any

from processors.tts_engine import create_voice
from utils.retry import RetryStrategy


class TTSService:
    """TTS service wrapper around the current engine function."""

    def __init__(self, retry_strategy: RetryStrategy | None = None, logger: Any = None):
        self.retry_strategy = retry_strategy
        self.logger = logger

    def create_voice(self, text: str, output_file: Path, voice_cfg: dict, google_key_dir: str) -> None:
        if self.retry_strategy:
            self.retry_strategy.run(
                lambda: create_voice(text, output_file, voice_cfg, google_key_dir),
                "tts_create_voice",
                "tts",
            )
            return
        create_voice(text, output_file, voice_cfg, google_key_dir)
