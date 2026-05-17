from __future__ import annotations
from pathlib import Path
import json
import time
import traceback
from typing import Any

from processors.text_matcher import find_text_for_video, srt_to_plain_text
from processors.tts_engine import create_voice
from processors.render_engine import render_video
from processors.sheet_client import SheetConfig, to_bool, to_float, to_int

ROOT = Path(__file__).resolve().parent


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def safe_name(name: str) -> str:
    return ''.join(c if c.isalnum() or c in '._- ' else '_' for c in name).strip()


def parse_list(value: Any) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in str(value).split(',') if x.strip()]


def resolve_path(value: Any) -> str:
    """Cho phép để trống asset trong Sheet. Path tương đối sẽ tính từ thư mục project."""
    if not value:
        return ''
    p = Path(str(value))
    if p.is_absolute():
        return str(p)
    return str((ROOT / p).resolve())


def normalize_channel(row: dict) -> dict:
    return {
        'enabled': to_bool(row.get('enabled'), True),
        'input_folder': row.get('input_folder', ''),
        'output_folder': row.get('output_folder', ''),
        'voice_id': row.get('voice_id', ''),
        'music_pack_id': row.get('music_pack_id', ''),
        'overlay_pack_id': row.get('overlay_pack_id', ''),
        'render_preset_id': row.get('render_preset_id', ''),
        'subtitle_style_id': row.get('subtitle_style_id', ''),
        'use_nvenc': to_bool(row.get('use_nvenc'), True),
        'background_blur': to_bool(row.get('background_blur'), True),
        'blur_strength': to_int(row.get('blur_strength'), 28),
        'speed': to_float(row.get('speed'), 1.0),
        'logo_path': resolve_path(row.get('logo_path', '')),
        'logo_opacity': to_float(row.get('logo_opacity'), 0.16),
        'logo_x': row.get('logo_x', 30),
        'logo_y': row.get('logo_y', 40),
        'music_path': resolve_path(row.get('music_path', '')),
        'music_volume': to_float(row.get('music_volume'), 0.07),
        'raw': row,
    }


def normalize_voice(row: dict) -> dict:
    return {
        'engine': row.get('engine', 'google'),
        'language_code': row.get('language_code', 'vi-VN'),
        'name': row.get('name', 'vi-VN-Wavenet-A'),
        'gender': row.get('gender', 'FEMALE'),
        'speaking_rate': to_float(row.get('speaking_rate'), 1.0),
        'pitch': to_float(row.get('pitch'), 0.0),
        'volume_gain_db': to_float(row.get('volume_gain_db'), 0.0),
        'command': row.get('command', ''),
        'ref_audio_path': resolve_path(row.get('ref_audio_path', '')),
        'active': to_bool(row.get('active'), True),
        'raw': row,
    }


def merge_pack_into_channel(channel: dict, music_packs: dict, overlay_packs: dict, render_presets: dict) -> dict:
    cfg = dict(channel)

    preset = render_presets.get(channel.get('render_preset_id', ''), {})
    if preset:
        cfg['background_blur'] = to_bool(preset.get('background_blur'), cfg.get('background_blur', True))
        cfg['blur_strength'] = to_int(preset.get('blur_strength'), cfg.get('blur_strength', 28))
        cfg['speed'] = to_float(preset.get('speed'), cfg.get('speed', 1.0))
        cfg['use_nvenc'] = to_bool(preset.get('use_nvenc'), cfg.get('use_nvenc', True))

    music = music_packs.get(channel.get('music_pack_id', ''), {})
    if music:
        cfg['music_path'] = resolve_path(music.get('music_path', cfg.get('music_path', '')))
        cfg['music_volume'] = to_float(music.get('music_volume'), cfg.get('music_volume', 0.07))

    overlay = overlay_packs.get(channel.get('overlay_pack_id', ''), {})
    if overlay:
        cfg['logo_path'] = resolve_path(overlay.get('logo_path', cfg.get('logo_path', '')))
        cfg['logo_opacity'] = to_float(overlay.get('logo_opacity'), cfg.get('logo_opacity', 0.16))
        cfg['logo_x'] = overlay.get('logo_x', cfg.get('logo_x', 30))
        cfg['logo_y'] = overlay.get('logo_y', cfg.get('logo_y', 40))
        cfg['background_blur'] = to_bool(overlay.get('background_blur'), cfg.get('background_blur', True))
        cfg['blur_strength'] = to_int(overlay.get('blur_strength'), cfg.get('blur_strength', 28))
    return cfg


def load_sheet_data(settings: dict):
    sheet = SheetConfig(settings['spreadsheet_id'], settings['service_account_json']).connect()
    channels = {k: normalize_channel(v) for k, v in sheet.map_by('CHANNEL_CONFIG', 'channel_id').items()}
    voices = {k: normalize_voice(v) for k, v in sheet.map_by('VOICE_CONFIG', 'voice_id').items()}
    music_packs = sheet.map_by('MUSIC_PACK', 'music_pack_id')
    overlay_packs = sheet.map_by('OVERLAY_PACK', 'overlay_pack_id')
    render_presets = sheet.map_by('RENDER_PRESET', 'render_preset_id')
    queue = sheet.rows('VIDEO_QUEUE')
    return sheet, channels, voices, music_packs, overlay_packs, render_presets, queue


def process_one_video(video: Path, text_file: Path, channel_id: str, channel_cfg: dict, voices: dict, settings: dict) -> str:
    temp_dir = ROOT / settings.get('temp_dir', 'runtime/temp') / channel_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_folder = Path(channel_cfg['output_folder'])
    job_name = safe_name(video.stem)
    voice_file = temp_dir / f"{job_name}_{int(time.time())}.mp3"
    output_file = output_folder / f"{channel_id}_{job_name}.mp4"

    try:
        print(f"▶ [{channel_id}] {video.name}")
        print(f"  ↳ Bắt text: {text_file.name}")
        text = srt_to_plain_text(text_file)
        if not text:
            raise ValueError('Text rỗng')
        voice_id = channel_cfg['voice_id']
        if voice_id not in voices:
            raise KeyError(f"Không thấy voice_id trong VOICE_CONFIG: {voice_id}")
        voice_cfg = voices[voice_id]
        if not voice_cfg.get('active', True):
            raise ValueError(f"Voice đang tắt active=FALSE: {voice_id}")
        print(f"  ↳ Tạo giọng: {voice_id}")
        create_voice(text, voice_file, voice_cfg, settings['google_key_dir'])
        print("  ↳ Render video theo Google Sheet config")
        render_video(video, voice_file, output_file, channel_cfg)
        print(f"  ✅ Xong: {output_file}")
        return str(output_file)
    finally:
        try:
            if voice_file.exists():
                voice_file.unlink()
        except OSError:
            pass


def process_folder_mode(channels: dict, voices: dict, music_packs: dict, overlay_packs: dict, render_presets: dict, settings: dict) -> None:
    video_exts = {x.lower() for x in settings.get('video_exts', ['.mp4'])}
    priority = settings.get('text_exts_priority', ['_vi.srt', '.srt', '.txt'])
    for channel_id, base_channel in channels.items():
        if not base_channel.get('enabled', True):
            print(f"⏭️ Bỏ qua kênh tắt: {channel_id}")
            continue
        channel_cfg = merge_pack_into_channel(base_channel, music_packs, overlay_packs, render_presets)
        input_folder = Path(channel_cfg['input_folder'])
        if not input_folder.exists():
            print(f"❌ [{channel_id}] Không thấy input_folder: {input_folder}")
            continue
        videos = [p for p in input_folder.iterdir() if p.is_file() and p.suffix.lower() in video_exts]
        print(f"\n===== KÊNH: {channel_id} | {len(videos)} video =====")
        for video in videos:
            text_file = find_text_for_video(video, input_folder, priority)
            if not text_file:
                print(f"- Bỏ qua {video.name}: chưa có .srt/.txt cùng tên")
                continue
            try:
                process_one_video(video, text_file, channel_id, channel_cfg, voices, settings)
            except Exception as e:
                print(f"  ❌ Lỗi job {video.name}: {e}")
                traceback.print_exc()


def process_queue_mode(sheet: SheetConfig, channels: dict, voices: dict, music_packs: dict, overlay_packs: dict, render_presets: dict, queue: list[dict], settings: dict) -> None:
    new_status = settings.get('queue_status_new', 'NEW')
    priority = settings.get('text_exts_priority', ['_vi.srt', '.srt', '.txt'])
    jobs = [r for r in queue if str(r.get('status', '')).strip().upper() == new_status.upper()]
    print(f"\n===== VIDEO_QUEUE | {len(jobs)} job NEW =====")
    for job in jobs:
        job_id = str(job.get('job_id', '')).strip()
        channel_id = str(job.get('channel_id', '')).strip()
        try:
            if not job_id:
                raise ValueError('Thiếu job_id')
            if channel_id not in channels:
                raise KeyError(f'Không thấy channel_id: {channel_id}')
            base_channel = channels[channel_id]
            channel_cfg = merge_pack_into_channel(base_channel, music_packs, overlay_packs, render_presets)
            video = Path(str(job.get('video_path', '')).strip())
            if not video.exists():
                raise FileNotFoundError(f'Không thấy video_path: {video}')
            text_path_raw = str(job.get('text_path', '')).strip()
            text_file = Path(text_path_raw) if text_path_raw else find_text_for_video(video, video.parent, priority)
            if not text_file or not text_file.exists():
                raise FileNotFoundError(f'Không thấy txt/srt cho video: {video.name}')
            sheet.update_status_by_job_id(job_id, settings.get('queue_status_processing', 'PROCESSING'))
            output = process_one_video(video, text_file, channel_id, channel_cfg, voices, settings)
            sheet.update_status_by_job_id(job_id, settings.get('queue_status_done', 'READY_UPLOAD'), output_path=output, error='')
        except Exception as e:
            print(f"❌ Queue job lỗi {job_id}: {e}")
            traceback.print_exc()
            if job_id:
                try:
                    sheet.update_status_by_job_id(job_id, settings.get('queue_status_error', 'ERROR'), error=str(e))
                except Exception:
                    pass


def main() -> None:
    settings = load_json(ROOT / 'configs/settings.json')
    sheet, channels, voices, music_packs, overlay_packs, render_presets, queue = load_sheet_data(settings)
    if settings.get('process_queue_only', False):
        process_queue_mode(sheet, channels, voices, music_packs, overlay_packs, render_presets, queue, settings)
    else:
        process_folder_mode(channels, voices, music_packs, overlay_packs, render_presets, settings)


if __name__ == '__main__':
    main()
