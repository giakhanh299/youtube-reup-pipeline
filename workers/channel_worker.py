from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from logs.structured_logger import NullLogger
from processors.job_processor import VideoJobProcessor
from repositories.queue_persistence import QueueJobState
from services.channel_sheet_registry import ChannelSheetConfig
from services.text_service import TextService


@dataclass(frozen=True)
class ChannelWorkerResult:
    channel_id: str
    video_path: str
    status: str
    output_path: str = ""
    youtube_video_id: str = ""
    error: str = ""


class ChannelWorker:
    """Processes input folders using Google Sheet channel rows as source of truth."""

    def __init__(
        self,
        registry: Any,
        job_processor: VideoJobProcessor,
        uploader: Any,
        settings: dict,
        voices: dict | None = None,
        music_packs: dict | None = None,
        overlay_packs: dict | None = None,
        render_presets: dict | None = None,
        text_service: TextService | None = None,
        logger: Any = None,
    ):
        self.registry = registry
        self.job_processor = job_processor
        self.uploader = uploader
        self.settings = dict(settings)
        self.voices = voices or {}
        self.music_packs = music_packs or {}
        self.overlay_packs = overlay_packs or {}
        self.render_presets = render_presets or {}
        self.text_service = text_service or TextService()
        self.logger = logger or NullLogger()

    def _video_files(self, input_folder: str) -> list[Path]:
        folder = Path(input_folder)
        if not folder.exists():
            raise FileNotFoundError(f"input_folder not found: {folder}")
        if not folder.is_dir():
            raise ValueError(f"input_folder is not a directory: {folder}")
        video_exts = {str(ext).lower() for ext in self.settings.get("video_exts", [".mp4", ".mkv", ".avi", ".mov"])}
        return sorted(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in video_exts)

    def _channel_cfg(self, channel: ChannelSheetConfig) -> dict:
        output_root = Path(self.settings.get("render_output_dir", "runtime/rendered"))
        if not output_root.is_absolute():
            output_root = Path.cwd() / output_root
        cfg = {
            "enabled": channel.enabled,
            "input_folder": channel.input_folder,
            "output_folder": channel.output_folder or str(output_root / channel.channel_id),
            "voice_id": channel.voice_id,
            "music_pack_id": channel.music_pack_id,
            "overlay_pack_id": channel.overlay_pack_id,
            "render_preset_id": channel.render_preset_id,
            "use_nvenc": self.settings.get("use_nvenc", True),
            "background_blur": self.settings.get("background_blur", True),
            "blur_strength": self.settings.get("blur_strength", 28),
            "speed": self.settings.get("speed", 1.0),
        }
        preset = self.render_presets.get(channel.render_preset_id, {})
        if preset:
            cfg.update(preset)
        music = self.music_packs.get(channel.music_pack_id, {})
        if music:
            cfg.update(music)
        overlay = self.overlay_packs.get(channel.overlay_pack_id, {})
        if overlay:
            cfg.update(overlay)
        return cfg

    def _voices(self, channel: ChannelSheetConfig) -> dict:
        if channel.voice_id and channel.voice_id in self.voices:
            voices = dict(self.voices)
            voice_cfg = dict(voices[channel.voice_id])
            voice_cfg["engine"] = "omnivoice_local"
            voice_cfg["tts_engine"] = "omnivoice_local"
            voices[channel.voice_id] = voice_cfg
            return voices
        return {
            channel.voice_id or "sheet_omnivoice": {
                "active": True,
                "engine": "omnivoice_local",
                "tts_engine": "omnivoice_local",
                "language": self.settings.get("omnivoice_default_language", "vi"),
            }
        }

    def _job_row(self, channel: ChannelSheetConfig, video: Path) -> dict:
        row = dict(channel.raw or {})
        row.update(
            {
                "channel_id": channel.channel_id,
                "video_path": str(video),
                "voice_name": channel.voice_name,
                "ref_audio_path": channel.voice_path or row.get("ref_audio_path", ""),
                "reference_audio": channel.voice_path or row.get("reference_audio", ""),
                "voice_path": channel.voice_path or row.get("voice_path", ""),
                "ref_text": channel.ref_text or row.get("ref_text", ""),
                "privacyStatus": channel.privacy_status or "private",
                "youtube_oauth_token_json": channel.youtube_oauth_token_json,
            }
        )
        return row

    def _upload_job(self, channel: ChannelSheetConfig, video: Path, output_path: str) -> QueueJobState:
        return QueueJobState(
            job_id=f"{channel.channel_id}:{video.stem}",
            status="READY_UPLOAD",
            channel_id=channel.channel_id,
            video_path=str(video),
            output_path=output_path,
            title=video.stem,
            privacy_status=channel.privacy_status or "private",
            channel_key=channel.channel_id,
            account_name=channel.channel_name,
            youtube_token_path=channel.youtube_oauth_token_json,
        )

    def process(self, max_channels: int | None = None) -> list[ChannelWorkerResult]:
        settings = dict(self.settings)
        settings["voice_engine"] = "omnivoice_local"
        results: list[ChannelWorkerResult] = []
        channels = self.registry.enabled_channels(max_channels=max_channels)
        priority = settings.get("text_exts_priority", ["_vi.srt", ".vi.srt", ".srt", ".txt"])
        for channel in channels:
            processed_for_channel = 0
            try:
                for video in self._video_files(channel.input_folder):
                    if channel.daily_limit and processed_for_channel >= channel.daily_limit:
                        break
                    text_file = self.text_service.find_for_video(video, video.parent, priority)
                    output = self.job_processor.process_one_video(
                        video,
                        text_file,
                        channel.channel_id,
                        self._channel_cfg(channel),
                        self._voices(channel),
                        settings,
                        job_row=self._job_row(channel, video),
                    )
                    upload_id = ""
                    if self.uploader is not None:
                        upload_id = self.uploader.upload(self._upload_job(channel, video, output))
                    results.append(ChannelWorkerResult(channel.channel_id, str(video), "done", output, upload_id))
                    processed_for_channel += 1
            except Exception as exc:
                self.logger.error("channel_worker_failed", channel_id=channel.channel_id, error=str(exc))
                results.append(ChannelWorkerResult(channel.channel_id, channel.input_folder, "error", error=str(exc)))
        return results
