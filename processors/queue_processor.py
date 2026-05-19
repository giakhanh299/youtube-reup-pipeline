from __future__ import annotations

from pathlib import Path
import traceback
from typing import Any

from logs.structured_logger import NullLogger
from processors.job_processor import VideoJobProcessor
from repositories.queue_persistence import NullQueuePersistence, QueueJobState, QueuePersistence
from repositories.sheet_repository import SheetRepository
from services.text_service import TextService


class QueueProcessor:
    """Processes VIDEO_QUEUE rows."""

    def __init__(
        self,
        sheet_repository: SheetRepository,
        job_processor: VideoJobProcessor,
        text_service: TextService | None = None,
        logger: Any = None,
        queue_persistence: QueuePersistence | None = None,
    ):
        self.sheet_repository = sheet_repository
        self.job_processor = job_processor
        self.text_service = text_service or TextService()
        self.logger = logger or NullLogger()
        self.queue_persistence = queue_persistence or NullQueuePersistence()

    def process(
        self,
        channels: dict,
        voices: dict,
        music_packs: dict,
        overlay_packs: dict,
        render_presets: dict,
        queue: list[dict],
        settings: dict,
    ) -> None:
        new_status = settings.get("queue_status_new", "NEW")
        priority = settings.get("text_exts_priority", ["_vi.srt", ".srt", ".txt"])
        jobs = [r for r in queue if str(r.get("status", "")).strip().upper() == new_status.upper()]
        print(f"\n===== VIDEO_QUEUE | {len(jobs)} job NEW =====")
        for job in jobs:
            job_id = str(job.get("job_id", "")).strip()
            channel_id = str(job.get("channel_id", "")).strip()
            try:
                if not job_id:
                    raise ValueError("Missing job_id")
                if channel_id not in channels:
                    raise KeyError(f"channel_id not found: {channel_id}")
                base_channel = channels[channel_id]
                channel_cfg = self.sheet_repository.merge_pack_into_channel(
                    base_channel,
                    music_packs,
                    overlay_packs,
                    render_presets,
                )
                video = Path(str(job.get("video_path", "")).strip())
                if not video.exists():
                    raise FileNotFoundError(f"video_path not found: {video}")
                text_path_raw = str(job.get("text_path", "")).strip()
                text_file = Path(text_path_raw) if text_path_raw else self.text_service.find_for_video(video, video.parent, priority)
                if not text_file or not text_file.exists():
                    raise FileNotFoundError(f"txt/srt not found for video: {video.name}")
                self.queue_persistence.save_job_state(
                    QueueJobState(
                        job_id=job_id,
                        status=settings.get("queue_status_processing", "PROCESSING"),
                        channel_id=channel_id,
                        video_path=str(video),
                    )
                )
                self.sheet_repository.update_status_by_job_id(
                    job_id,
                    settings.get("queue_status_processing", "PROCESSING"),
                )
                output = self.job_processor.process_one_video(video, text_file, channel_id, channel_cfg, voices, settings)
                self.sheet_repository.update_status_by_job_id(
                    job_id,
                    settings.get("queue_status_done", "READY_UPLOAD"),
                    output_path=output,
                    error="",
                )
                self.queue_persistence.save_job_state(
                    QueueJobState(
                        job_id=job_id,
                        status=settings.get("queue_status_done", "READY_UPLOAD"),
                        channel_id=channel_id,
                        video_path=str(video),
                        output_path=output,
                    )
                )
            except Exception as exc:
                print(f"ERROR queue job {job_id}: {exc}")
                self.logger.error("queue_job_failed", job_id=job_id, channel_id=channel_id, error=str(exc))
                traceback.print_exc()
                if job_id:
                    self.queue_persistence.mark_failed(job_id, str(exc))
                    try:
                        self.sheet_repository.update_status_by_job_id(
                            job_id,
                            settings.get("queue_status_error", "ERROR"),
                            error=str(exc),
                        )
                    except Exception:
                        pass
