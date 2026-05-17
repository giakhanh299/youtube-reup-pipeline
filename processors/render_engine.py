from __future__ import annotations
from pathlib import Path
import subprocess


def file_exists_nonempty(path_value) -> bool:
    if not path_value:
        return False
    p = Path(path_value)
    return p.exists() and p.is_file()


def render_video(input_video: Path, voice_audio: Path, output_video: Path, channel_cfg: dict) -> None:
    """Render chính: video + voice + optional music + optional logo + optional blur bg."""
    output_video.parent.mkdir(parents=True, exist_ok=True)

    inputs = ['-i', str(input_video), '-i', str(voice_audio)]
    music_path = channel_cfg.get('music_path')
    logo_path = channel_cfg.get('logo_path')
    has_music = file_exists_nonempty(music_path)
    has_logo = file_exists_nonempty(logo_path)

    if has_music:
        inputs += ['-stream_loop', '-1', '-i', str(Path(music_path))]
    if has_logo:
        inputs += ['-i', str(Path(logo_path))]

    filters = []
    video_label = '[0:v]'

    speed = float(channel_cfg.get('speed', 1.0) or 1.0)

    if channel_cfg.get('background_blur', True):
        blur = int(channel_cfg.get('blur_strength', 28))
        filters.append(f"[0:v]scale=1080:1920,boxblur={blur}:1,setpts={1/speed:.6f}*PTS[bg]")
        filters.append(f"[0:v]scale=900:-1,setpts={1/speed:.6f}*PTS[fg]")
        filters.append("[bg][fg]overlay=(W-w)/2:(H-h)/2[vbase]")
        video_label = '[vbase]'

    if has_logo:
        logo_input_index = 3 if has_music else 2
        opacity = float(channel_cfg.get('logo_opacity', 0.16))
        x = channel_cfg.get('logo_x', 30)
        y = channel_cfg.get('logo_y', 40)
        filters.append(f"[{logo_input_index}:v]format=rgba,colorchannelmixer=aa={opacity}[logo]")
        filters.append(f"{video_label}[logo]overlay={x}:{y}[vout]")
        video_label = '[vout]'

    # voice audio giữ nguyên tốc độ vì TTS đã sinh theo text; speed chỉ áp dụng cho video hình.
    if has_music:
        vol = float(channel_cfg.get('music_volume', 0.07))
        filters.append(f"[2:a]volume={vol}[music]")
        filters.append("[1:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]")
        audio_label = '[aout]'
    else:
        audio_label = '1:a:0'

    cmd = ['ffmpeg', '-y', '-loglevel', 'error', *inputs]

    if filters:
        cmd += ['-filter_complex', ';'.join(filters), '-map', video_label, '-map', audio_label]
    else:
        cmd += ['-map', '0:v:0', '-map', '1:a:0']

    if channel_cfg.get('use_nvenc', True):
        cmd += ['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '23']
    else:
        cmd += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23']

    cmd += ['-c:a', 'aac', '-b:a', '192k', '-shortest', str(output_video)]
    subprocess.run(cmd, check=True)
