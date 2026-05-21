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
            voice_done = False
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
                video = Path(self.sheet_repository.resolve_path(str(job.get("video_path", "")).strip()))
                if not video.exists():
                    raise FileNotFoundError(f"video_path not found: {video}")
                row_text = str(
                    job.get("script_text")
                    or job.get("tts_text")
                    or job.get("text")
                    or job.get("title_vi")
                    or job.get("title")
                    or ""
                ).strip()
                text_path_raw = str(job.get("text_path", "")).strip()
                text_file = Path(self.sheet_repository.resolve_path(text_path_raw)) if text_path_raw else self.text_service.find_for_video(video, video.parent, priority)
                if not row_text and (not text_file or not text_file.exists()):
                    raise FileNotFoundError(f"txt/srt not found for video: {video.name}")
                self.queue_persistence.save_job_state(
                    QueueJobState(
                        job_id=job_id,
                        status=settings.get("queue_status_processing", "PROCESSING"),
                        channel_id=channel_id,
                        video_path=str(video),
                        channel_key=str(job.get("channel_key", "")).strip(),
                        account_name=str(job.get("account_name", "")).strip(),
                        youtube_token_path=str(job.get("youtube_token_path", "")).strip(),
                    )
                )
                self.sheet_repository.update_status_by_job_id(
                    job_id,
                    settings.get("queue_status_processing", "PROCESSING"),
                )
                self.sheet_repository.update_video_queue_fields_by_job_id(
                    job_id,
                    {"voice_status": "processing", "voice_error": ""},
                )
                output = self.job_processor.process_one_video(
                    video,
                    text_file,
                    channel_id,
                    channel_cfg,
                    voices,
                    settings,
                    job_row=job,
                )
                voice_output = str(job.get("voice_output_path") or job.get("output_audio_path") or "").strip()
                voice_fields = {"voice_status": "done", "voice_error": ""}
                if voice_output:
                    voice_fields["voice_output_path"] = voice_output
                self.sheet_repository.update_video_queue_fields_by_job_id(job_id, voice_fields)
                voice_done = True
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
                        title=str(job.get("title", "")).strip(),
                        description=str(job.get("description", "")).strip(),
                        tags=[item.strip() for item in str(job.get("tags", "")).split(",") if item.strip()],
                        category_id=str(job.get("categoryId", job.get("category_id", ""))).strip(),
                        privacy_status=str(
                            job.get("privacyStatus", job.get("privacy_status", ""))
                            or settings.get("youtube_default_privacy", "private")
                        ).strip(),
                        channel_key=str(job.get("channel_key", "")).strip(),
                        account_name=str(job.get("account_name", "")).strip(),
                        youtube_token_path=str(job.get("youtube_token_path", "")).strip(),
                    )
                )
            except Exception as exc:
                print(f"ERROR queue job {job_id}: {exc}")
                self.logger.error("queue_job_failed", job_id=job_id, channel_id=channel_id, error=str(exc))
                traceback.print_exc()
                if job_id:
                    self.queue_persistence.mark_failed(job_id, str(exc))
                    if not voice_done:
                        try:
                            self.sheet_repository.update_video_queue_fields_by_job_id(
                                job_id,
                                {"voice_status": "error", "voice_error": str(exc)},
                            )
                        except Exception:
                            pass
                    try:
                        self.sheet_repository.update_status_by_job_id(
                            job_id,
                            settings.get("queue_status_error", "ERROR"),
                            error=str(exc),
                        )
                    except Exception:
                        pass
