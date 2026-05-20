from __future__ import annotations

from pathlib import Path

from services.render_service import RenderService


def file_exists_nonempty(path_value) -> bool:
    if not path_value:
        return False
    path = Path(path_value)
    return path.exists() and path.is_file()


def render_video(input_video: Path, voice_audio: Path, output_video: Path, channel_cfg: dict) -> None:
    """Backward-compatible render entrypoint."""
    RenderService().render_video(input_video, voice_audio, output_video, channel_cfg)
