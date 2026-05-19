from __future__ import annotations

from pathlib import Path
from typing import Any

from processors.render_engine import render_video
from utils.retry import RetryStrategy, retry_ffmpeg


class RenderService:
    """Render service wrapper around the current FFmpeg renderer."""

    def __init__(self, retry_strategy: RetryStrategy | None = None, logger: Any = None):
        self.retry_strategy = retry_strategy
        self.logger = logger

    def render_video(self, input_video: Path, voice_audio: Path, output_video: Path, channel_cfg: dict) -> None:
        if self.retry_strategy:
            retry_ffmpeg(
                lambda: render_video(input_video, voice_audio, output_video, channel_cfg),
                self.retry_strategy,
                "ffmpeg_render_video",
            )
            return
        render_video(input_video, voice_audio, output_video, channel_cfg)
