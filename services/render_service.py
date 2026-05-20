from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

from utils.retry import RetryStrategy, retry_ffmpeg


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return default


def _file_exists(path_value: Any) -> bool:
    if not path_value:
        return False
    path = Path(str(path_value))
    return path.exists() and path.is_file()


def _target_size(channel_cfg: dict) -> tuple[int, int]:
    width = _to_int(channel_cfg.get("output_width"), 0)
    height = _to_int(channel_cfg.get("output_height"), 0)
    aspect = str(channel_cfg.get("aspect_ratio", "")).strip().lower()
    if width > 0 and height > 0:
        return width, height
    if aspect in {"16:9", "landscape"}:
        return 1920, 1080
    if aspect in {"1:1", "square"}:
        return 1080, 1080
    return 1080, 1920


def _video_filter(input_label: str, channel_cfg: dict) -> tuple[list[str], str]:
    width, height = _target_size(channel_cfg)
    fit_mode = str(
        channel_cfg.get("fit_mode")
        or ("blur_bg" if _to_bool(channel_cfg.get("background_blur"), True) else "contain")
    ).strip().lower()
    speed = max(_to_float(channel_cfg.get("speed"), 1.0), 0.01)
    setpts = f"setpts={1 / speed:.6f}*PTS"

    if fit_mode in {"cover", "crop"}:
        return [
            f"{input_label}scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},{setpts}[vbase]"
        ], "[vbase]"

    if fit_mode == "blur_bg":
        blur_strength = _to_int(channel_cfg.get("blur_strength"), 28)
        fg_width = _to_int(channel_cfg.get("foreground_width"), int(width * 0.84))
        return [
            f"{input_label}scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},gblur=sigma={blur_strength},{setpts}[bg]",
            f"{input_label}scale={fg_width}:-2:force_original_aspect_ratio=decrease,{setpts}[fg]",
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[vbase]",
        ], "[vbase]"

    return [
        f"{input_label}scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,{setpts}[vbase]"
    ], "[vbase]"


def _subtitle_filter(path_value: Any) -> str:
    subtitle_path = str(path_value).replace("\\", "/").replace(":", "\\:")
    return f"subtitles='{subtitle_path}'"


def build_render_command(input_video: Path, voice_audio: Path | None, output_video: Path, channel_cfg: dict) -> list[str]:
    inputs = ["-i", str(input_video)]
    next_input_index = 1
    voice_index = None
    if voice_audio:
        inputs += ["-i", str(voice_audio)]
        voice_index = next_input_index
        next_input_index += 1

    music_path = channel_cfg.get("music_path")
    logo_path = channel_cfg.get("logo_path")
    subtitle_path = channel_cfg.get("subtitle_path") or channel_cfg.get("subtitles_path")
    has_music = _file_exists(music_path)
    has_logo = _file_exists(logo_path)
    has_subtitles = _file_exists(subtitle_path)

    music_index = None
    logo_index = None
    if has_music:
        inputs += ["-stream_loop", "-1", "-i", str(Path(str(music_path)))]
        music_index = next_input_index
        next_input_index += 1
    if has_logo:
        inputs += ["-i", str(Path(str(logo_path)))]
        logo_index = next_input_index

    filters, video_label = _video_filter("[0:v]", channel_cfg)

    if has_subtitles:
        filters.append(f"{video_label}{_subtitle_filter(subtitle_path)}[vsub]")
        video_label = "[vsub]"

    if has_logo and logo_index is not None:
        opacity = _to_float(channel_cfg.get("logo_opacity"), 0.16)
        x = channel_cfg.get("logo_x", 30)
        y = channel_cfg.get("logo_y", 40)
        logo_width = _to_int(channel_cfg.get("logo_width"), 0)
        logo_filter = f"[{logo_index}:v]format=rgba"
        if logo_width > 0:
            logo_filter += f",scale={logo_width}:-1"
        logo_filter += f",colorchannelmixer=aa={opacity}[logo]"
        filters.append(logo_filter)
        filters.append(f"{video_label}[logo]overlay={x}:{y}[vout]")
        video_label = "[vout]"

    audio_inputs = []
    keep_original_audio = _to_bool(channel_cfg.get("keep_original_audio"), False)
    original_audio_volume = _to_float(channel_cfg.get("original_audio_volume"), 0.0 if voice_index is not None else 1.0)
    tts_audio_volume = _to_float(channel_cfg.get("tts_audio_volume"), 1.0)
    music_volume = _to_float(channel_cfg.get("music_volume"), 0.07)

    if keep_original_audio and original_audio_volume > 0:
        filters.append(f"[0:a]volume={original_audio_volume}[aorig]")
        audio_inputs.append("[aorig]")
    if voice_index is not None:
        filters.append(f"[{voice_index}:a]volume={tts_audio_volume}[atts]")
        audio_inputs.append("[atts]")
    if has_music and music_index is not None:
        filters.append(f"[{music_index}:a]volume={music_volume}[amusic]")
        audio_inputs.append("[amusic]")

    audio_label = ""
    if len(audio_inputs) > 1:
        filters.append(f"{''.join(audio_inputs)}amix=inputs={len(audio_inputs)}:duration=first:dropout_transition=2[aout]")
        audio_label = "[aout]"
    elif len(audio_inputs) == 1:
        audio_label = audio_inputs[0]
    elif voice_index is not None:
        audio_label = f"{voice_index}:a:0"
    elif keep_original_audio:
        audio_label = "0:a:0"

    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters), "-map", video_label]
    if audio_label:
        cmd += ["-map", audio_label]

    if _to_bool(channel_cfg.get("use_nvenc"), True):
        cmd += ["-c:v", "h264_nvenc", "-preset", str(channel_cfg.get("nvenc_preset", "p4")), "-cq", str(channel_cfg.get("cq", 23))]
    else:
        cmd += ["-c:v", "libx264", "-preset", str(channel_cfg.get("x264_preset", "veryfast")), "-crf", str(channel_cfg.get("crf", 23))]

    if audio_label:
        cmd += ["-c:a", "aac", "-b:a", str(channel_cfg.get("audio_bitrate", "192k"))]
    cmd += ["-shortest", str(output_video)]
    return cmd


class RenderService:
    """FFmpeg render service for Shorts/TikTok-style outputs."""

    def __init__(self, retry_strategy: RetryStrategy | None = None, logger: Any = None):
        self.retry_strategy = retry_strategy
        self.logger = logger

    def build_command(self, input_video: Path, voice_audio: Path | None, output_video: Path, channel_cfg: dict) -> list[str]:
        return build_render_command(input_video, voice_audio, output_video, channel_cfg)

    def render_video(self, input_video: Path, voice_audio: Path, output_video: Path, channel_cfg: dict) -> None:
        output_video.parent.mkdir(parents=True, exist_ok=True)
        cmd = self.build_command(input_video, voice_audio, output_video, channel_cfg)
        if self.retry_strategy:
            retry_ffmpeg(lambda: subprocess.run(cmd, check=True), self.retry_strategy, "ffmpeg_render_video")
            return
        subprocess.run(cmd, check=True)
