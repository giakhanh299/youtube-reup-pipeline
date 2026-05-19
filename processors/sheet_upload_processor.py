from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from integrations.youtube.youtube_api_uploader import parse_tags
from logs.structured_logger import NullLogger
from repositories.queue_persistence import QueueJobState
from repositories.sheet_repository import SheetRepository


@dataclass(frozen=True)
class SheetUploadResult:
    row_number: int
    video_path: str
    status: str
    youtube_video_id: str = ""
    error: str = ""


class SheetUploadProcessor:
    """Uploads rows from the real upload control sheet."""

    def __init__(
        self,
        sheet_repository: SheetRepository,
        uploader: Any,
        logger: Any = None,
    ):
        self.sheet_repository = sheet_repository
        self.uploader = uploader
        self.logger = logger or NullLogger()

    def _job_from_row(self, row_number: int, row: dict, settings: dict) -> QueueJobState:
        video_path = str(row.get("video_path", "")).strip()
        if not video_path:
            raise ValueError("video_path is required")
        resolved_video_path = (
            self.sheet_repository.resolve_path(video_path)
            if hasattr(self.sheet_repository, "resolve_path")
            else video_path
        )
        if not Path(resolved_video_path).exists():
            raise FileNotFoundError(f"video_path not found: {resolved_video_path}")
        privacy_status = str(row.get("privacyStatus", "") or settings.get("youtube_default_privacy", "private")).strip()
        category_id = str(row.get("categoryId", "") or settings.get("youtube_default_category_id", "22")).strip()
        return QueueJobState(
            job_id=f"sheet_row_{row_number}",
            status="READY_UPLOAD",
            output_path=resolved_video_path,
            title=str(row.get("title", "")).strip() or Path(resolved_video_path).stem,
            description=str(row.get("description", "")).strip(),
            tags=parse_tags(row.get("tags", "")),
            category_id=category_id or "22",
            privacy_status=privacy_status or "private",
        )

    def process(self, settings: dict) -> list[SheetUploadResult]:
        worksheet_name = settings.get("upload_sheet_name", "Video đã edit")
        pending_status = str(settings.get("upload_status_new", "pending")).strip().lower()
        uploading_status = settings.get("upload_status_uploading", "uploading")
        done_status = settings.get("upload_status_done", "uploaded")
        error_status = settings.get("upload_status_error", "failed")

        results: list[SheetUploadResult] = []
        for row_number, row in self.sheet_repository.load_upload_jobs(worksheet_name):
            current_status = str(row.get("upload_status", "")).strip().lower()
            if current_status and current_status != pending_status:
                continue
            video_path = str(row.get("video_path", "")).strip()
            try:
                job = self._job_from_row(row_number, row, settings)
                self.sheet_repository.update_upload_result(worksheet_name, row_number, uploading_status)
                upload_id = self.uploader.upload(job)
                upload_time = datetime.now(timezone.utc).isoformat()
                self.sheet_repository.update_upload_result(
                    worksheet_name,
                    row_number,
                    done_status,
                    youtube_video_id=upload_id,
                    upload_error="",
                    upload_time=upload_time,
                )
                self.logger.upload(
                    "sheet_upload_finished",
                    row_number=row_number,
                    video_path=job.output_path,
                    youtube_video_id=upload_id,
                )
                results.append(SheetUploadResult(row_number, job.output_path, done_status, upload_id))
            except Exception as exc:
                self.sheet_repository.update_upload_result(
                    worksheet_name,
                    row_number,
                    error_status,
                    upload_error=str(exc),
                )
                self.logger.error("sheet_upload_failed", row_number=row_number, video_path=video_path, error=str(exc))
                results.append(SheetUploadResult(row_number, video_path, error_status, error=str(exc)))
        return results
