from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable

from integrations.youtube.youtube_api_uploader import YouTubeApiUploader
from logs.structured_logger import NullLogger
from repositories.queue_persistence import QueueJobState


@dataclass(frozen=True)
class AccountWorkerAssignment:
    account_name: str
    channel_key: str = ""
    youtube_token_path: str = ""
    worker_index: int = 0


class MultiAccountUploader:
    """Routes upload jobs to isolated per-account uploader instances."""

    def __init__(
        self,
        settings: dict,
        uploader_factory: Callable[[dict], Any] | None = None,
        worker_count: int | None = None,
        logger: Any = None,
    ):
        self.settings = dict(settings)
        self.worker_count = int(worker_count or settings.get("upload_worker_count", 1) or 1)
        self.logger = logger or NullLogger()
        self.uploader_factory = uploader_factory or (lambda account_settings: YouTubeApiUploader.from_settings(account_settings, logger=self.logger))
        self._uploaders: dict[str, Any] = {}
        self._tokens_by_account: dict[str, str] = {}
        self._locks: dict[str, Lock] = {}

    def _account_name_for(self, job: QueueJobState) -> str:
        return job.account_name or job.channel_key or "default"

    def _assignment_for(self, job: QueueJobState) -> AccountWorkerAssignment:
        account_name = self._account_name_for(job)
        worker_index = abs(hash(account_name)) % max(self.worker_count, 1)
        return AccountWorkerAssignment(
            account_name=account_name,
            channel_key=job.channel_key,
            youtube_token_path=job.youtube_token_path,
            worker_index=worker_index,
        )

    def _settings_for(self, assignment: AccountWorkerAssignment) -> dict:
        settings = dict(self.settings)
        if assignment.youtube_token_path:
            settings["youtube_oauth_token_json"] = assignment.youtube_token_path
        return settings

    def _uploader_for(self, assignment: AccountWorkerAssignment) -> Any:
        account_name = assignment.account_name
        token_path = assignment.youtube_token_path or self.settings.get("youtube_oauth_token_json", "")
        existing_token = self._tokens_by_account.get(account_name)
        if existing_token and token_path and existing_token != token_path:
            raise ValueError(f"token path conflict for account: {account_name}")
        self._tokens_by_account[account_name] = token_path
        if account_name not in self._uploaders:
            self._uploaders[account_name] = self.uploader_factory(self._settings_for(assignment))
        return self._uploaders[account_name]

    def upload(self, job: QueueJobState) -> str:
        assignment = self._assignment_for(job)
        lock = self._locks.setdefault(assignment.account_name, Lock())
        self.logger.worker(
            "upload_worker_assigned",
            job_id=job.job_id,
            account_name=assignment.account_name,
            channel_key=assignment.channel_key,
            worker_index=assignment.worker_index,
        )
        with lock:
            return self._uploader_for(assignment).upload(job)
