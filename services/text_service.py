from __future__ import annotations

from pathlib import Path

from processors.text_matcher import find_text_for_video, srt_to_plain_text


class TextService:
    """Text matching and subtitle parsing service."""

    def find_for_video(self, video_path: Path, folder: Path, priority: list[str]) -> Path | None:
        return find_text_for_video(video_path, folder, priority)

    def to_plain_text(self, file_path: Path) -> str:
        return srt_to_plain_text(file_path)
