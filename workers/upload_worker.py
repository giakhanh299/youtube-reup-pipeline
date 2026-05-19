from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from integrations.telegram.notifier import TelegramNotifier
from logs.structured_logger import NullLogger
from repositories.queue_persistence import QueueJobState, QueuePersistence


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
    ):
        self.upload_client = upload_client
        self.queue_persistence = queue_persistence
        self.notifier = notifier or TelegramNotifier(enabled=False, logger=logger)
        self.logger = logger or NullLogger()

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
            self.queue_persistence.save_job_state(QueueJobState(**{**job.__dict__, "status": "UPLOADING"}))
            upload_id = self.upload_client.upload(job)
            self.queue_persistence.save_job_state(QueueJobState(**{**job.__dict__, "status": "UPLOADED"}))
            self.notifier.job_completed(job.job_id, job.channel_id, upload_id)
            self.logger.worker("upload_finished", job_id=job.job_id, upload_id=upload_id)
            return UploadWorkerResult(job.job_id, "UPLOADED", upload_id=upload_id)
        except Exception as exc:
            self.queue_persistence.mark_failed(job.job_id, str(exc))
            self.notifier.upload_failed(job.job_id, job.channel_id, str(exc))
            self.logger.worker("upload_failed", job_id=job.job_id, error=str(exc))
            return UploadWorkerResult(job.job_id, "ERROR", error=str(exc))
