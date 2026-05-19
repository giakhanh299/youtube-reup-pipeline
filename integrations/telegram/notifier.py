from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from logs.structured_logger import NullLogger


@dataclass(frozen=True)
class Notification:
    event: str
    message: str
    job_id: str = ""
    channel_id: str = ""


class TelegramNotifier:
    """Monitoring hook placeholder for future Telegram delivery."""

    def __init__(self, enabled: bool = False, logger: Any = None):
        self.enabled = enabled
        self.logger = logger or NullLogger()

    def notify(self, notification: Notification) -> None:
        self.logger.telegram(
            "notification_prepared",
            event_name=notification.event,
            message=notification.message,
            job_id=notification.job_id,
            channel_id=notification.channel_id,
            enabled=self.enabled,
        )

    def job_completed(self, job_id: str, channel_id: str, output_path: str) -> None:
        self.notify(Notification("job_completed", f"Job completed: {output_path}", job_id, channel_id))

    def upload_failed(self, job_id: str, channel_id: str, error: str) -> None:
        self.notify(Notification("upload_failed", error, job_id, channel_id))

    def retry_triggered(self, job_id: str, channel_id: str, error: str) -> None:
        self.notify(Notification("retry_triggered", error, job_id, channel_id))

    def render_failed(self, job_id: str, channel_id: str, error: str) -> None:
        self.notify(Notification("render_failed", error, job_id, channel_id))
