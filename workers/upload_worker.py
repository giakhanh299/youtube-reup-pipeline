from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol

from integrations.telegram.notifier import TelegramNotifier
from integrations.youtube.youtube_api_uploader import UploadState, YouTubeApiUploader
from logs.structured_logger import NullLogger
from repositories.queue_persistence import QueueJobState, QueuePersistence
from utils.retry import RetryStrategy


class UploadClient(Protocol):
    def upload(self, job: QueueJobState) -> str:
        raise NotImplementedError


@dataclass
class UploadWorkerResult:
    job_id: str
    status: str
    upload_id: str = ""
    error: str = ""


class UploadWorker:
    """Architecture scaffold for resumable upload workers."""

    def __init__(
        self,
        upload_client: UploadClient | None,
        queue_persistence: QueuePersistence,
        notifier: TelegramNotifier | None = None,
        logger: Any = None,
        ledger_repository: Any = None,
    ):
        self.upload_client = upload_client
        self.queue_persistence = queue_persistence
        self.notifier = notifier or TelegramNotifier(enabled=False, logger=logger)
        self.logger = logger or NullLogger()
        self.ledger_repository = ledger_repository

    def process_ready_jobs(self, jobs: Iterable[QueueJobState]) -> list[UploadWorkerResult]:
        results: list[UploadWorkerResult] = []
        for job in jobs:
            if job.status != "READY_UPLOAD":
                continue
            results.append(self.process_one(job))
        return results

    def process_one(self, job: QueueJobState) -> UploadWorkerResult:
        if self.upload_client is None:
            self.logger.worker("upload_skipped_no_client", job_id=job.job_id)
            return UploadWorkerResult(job.job_id, "SKIPPED", error="upload_client is not configured")

        try:
            self.queue_persistence.save_job_state(
                QueueJobState(**{**job.__dict__, "status": "UPLOADING", "upload_state": UploadState.UPLOADING})
            )
            upload_id = self.upload_client.upload(job)
            self.queue_persistence.save_job_state(
                QueueJobState(**{**job.__dict__, "status": "UPLOADED", "upload_state": UploadState.UPLOADED})
            )
            self.notifier.job_completed(job.job_id, job.channel_id, upload_id)
            if self.ledger_repository is not None:
                self.ledger_repository.upsert_uploaded_video(uploaded_ledger_row(job, upload_id))
            self.logger.worker("upload_finished", job_id=job.job_id, upload_id=upload_id)
            return UploadWorkerResult(job.job_id, "UPLOADED", upload_id=upload_id)
        except Exception as exc:
            self.queue_persistence.mark_failed(job.job_id, str(exc))
            self.notifier.upload_failed(job.job_id, job.channel_id, str(exc))
            self.logger.worker("upload_failed", job_id=job.job_id, error=str(exc))
            return UploadWorkerResult(job.job_id, "ERROR", error=str(exc))


def build_youtube_upload_worker(
    settings: dict,
    queue_persistence: QueuePersistence,
    retry_strategy: RetryStrategy | None = None,
    notifier: TelegramNotifier | None = None,
    logger: Any = None,
    ledger_repository: Any = None,
) -> UploadWorker:
    """Build an UploadWorker backed by YouTube Data API v3."""

    def save_upload_state(upload_state: str, job: QueueJobState) -> None:
        status = job.status
        if upload_state in {UploadState.PENDING, UploadState.UPLOADING, UploadState.RETRYING}:
            status = "UPLOADING"
        elif upload_state == UploadState.UPLOADED:
            status = "UPLOADED"
        elif upload_state == UploadState.FAILED:
            status = "ERROR"
        queue_persistence.save_job_state(
            QueueJobState(**{**job.__dict__, "status": status, "upload_state": upload_state})
        )

    uploader = YouTubeApiUploader.from_settings(
        settings,
        retry_strategy=retry_strategy,
        logger=logger,
        state_callback=save_upload_state,
    )
    return UploadWorker(uploader, queue_persistence, notifier=notifier, logger=logger, ledger_repository=ledger_repository)


def uploaded_ledger_row(job: QueueJobState, youtube_video_id: str) -> dict[str, str]:
    upload_time = datetime.now(timezone.utc).isoformat()
    youtube_url = f"https://www.youtube.com/watch?v={youtube_video_id}"
    title = job.title or ""
    description = job.description or ""
    tags = ",".join(job.tags or []) if isinstance(job.tags, list) else str(job.tags or "")
    return {
        "uploaded_id": f"{job.job_id}:{youtube_video_id}",
        "job_id": job.job_id,
        "channel_id": job.channel_id,
        "channel_name": "",
        "account_name": job.account_name,
        "source_channel_id": "",
        "source_url": "",
        "source_video_id": "",
        "original_title": title,
        "translated_title": "",
        "final_title": title,
        "final_description": description,
        "tags": tags,
        "categoryId": job.category_id,
        "privacyStatus": job.privacy_status or "private",
        "youtube_video_id": youtube_video_id,
        "youtube_url": youtube_url,
        "upload_time": upload_time,
        "video_path": job.video_path,
        "rendered_video_path": job.output_path,
        "voice_id": "",
        "render_preset_id": "",
        "upload_status": "uploaded",
        "ledger_status": "active",
        "notes": "",
    }
