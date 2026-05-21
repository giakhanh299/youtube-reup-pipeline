from __future__ import annotations

from pathlib import Path
import traceback
from typing import Any

from logs.structured_logger import NullLogger
from processors.job_processor import VideoJobProcessor
from repositories.sheet_repository import SheetRepository
from services.text_service import TextService


class FolderProcessor:
    """Processes videos discovered from per-channel input folders."""

    def __init__(
        self,
        sheet_repository: SheetRepository,
        job_processor: VideoJobProcessor,
        text_service: TextService | None = None,
        logger: Any = None,
    ):
        self.sheet_repository = sheet_repository
        self.job_processor = job_processor
        self.text_service = text_service or TextService()
        self.logger = logger or NullLogger()

    def process(
        self,
        channels: dict,
        voices: dict,
        music_packs: dict,
        overlay_packs: dict,
        render_presets: dict,
        settings: dict,
    ) -> None:
        video_exts = {x.lower() for x in settings.get("video_exts", [".mp4"])}
        priority = settings.get("text_exts_priority", ["_vi.srt", ".srt", ".txt"])
        for channel_id, base_channel in channels.items():
            if not base_channel.get("enabled", True):
                print(f"Skip disabled channel: {channel_id}")
                continue
            channel_cfg = self.sheet_repository.merge_pack_into_channel(
                base_channel,
                music_packs,
                overlay_packs,
                render_presets,
            )
            input_folder_raw = str(channel_cfg.get("input_folder", "")).strip()
            if not input_folder_raw:
                print(f"ERROR [{channel_id}] missing input_folder")
                continue
            input_folder = Path(self.sheet_repository.resolve_path(input_folder_raw))
            if not input_folder.exists():
                print(f"ERROR [{channel_id}] input_folder not found: {input_folder}")
                continue
            videos = [p for p in input_folder.iterdir() if p.is_file() and p.suffix.lower() in video_exts]
            print(f"\n===== CHANNEL: {channel_id} | {len(videos)} video =====")
            for video in videos:
                text_file = self.text_service.find_for_video(video, input_folder, priority)
                if not text_file:
                    print(f"- Skip {video.name}: missing matching .srt/.txt")
                    continue
                try:
                    self.job_processor.process_one_video(video, text_file, channel_id, channel_cfg, voices, settings)
                except Exception as exc:
                    print(f"  ERROR job {video.name}: {exc}")
                    self.logger.error("folder_job_failed", channel_id=channel_id, video=str(video), error=str(exc))
                    traceback.print_exc()
