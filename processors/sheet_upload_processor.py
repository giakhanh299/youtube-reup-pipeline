from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
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

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _to_int(self, value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(float(str(value)))
        except Exception:
            return default

    def _parse_time(self, value: Any) -> datetime | None:
        if not value:
            return None
        try:
            text = str(value).strip()
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None

    def _is_retryable_row(self, row: dict, settings: dict) -> bool:
        retry_count = self._to_int(row.get("retry_count", 0))
        max_attempts = int(settings.get("upload_retry_max_attempts", 3))
        return retry_count < max_attempts

    def _is_stale_uploading(self, row: dict, settings: dict) -> bool:
        started = self._parse_time(row.get("upload_started_at", ""))
        if not started:
            return True
        stale_after = float(settings.get("upload_recover_stale_after_seconds", 3600))
        age = (datetime.now(timezone.utc) - started).total_seconds()
        return age >= stale_after

    def _should_process_row(self, row: dict, settings: dict) -> bool:
        if str(row.get("youtube_video_id", "")).strip():
            return False
        current_status = str(row.get("upload_status", "")).strip().lower()
        done_status = str(settings.get("upload_status_done", "uploaded")).strip().lower()
        pending_status = str(settings.get("upload_status_new", "pending")).strip().lower()
        uploading_status = str(settings.get("upload_status_uploading", "uploading")).strip().lower()
        error_status = str(settings.get("upload_status_error", "failed")).strip().lower()
        if current_status == done_status:
            return False
        if not current_status or current_status == pending_status:
            return True
        if current_status == error_status:
            return self._is_retryable_row(row, settings)
        if current_status == uploading_status:
            return self._is_stale_uploading(row, settings) and self._is_retryable_row(row, settings)
        return False

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
        allowed_exts = {
            str(ext).lower()
            for ext in settings.get("upload_allowed_exts", settings.get("video_exts", [".mp4", ".mkv", ".avi", ".mov"]))
        }
        if Path(resolved_video_path).suffix.lower() not in allowed_exts:
            raise ValueError(f"unsupported upload file extension: {Path(resolved_video_path).suffix}")
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
            channel_key=str(row.get("channel_key", "")).strip(),
            account_name=str(row.get("account_name", "")).strip(),
            youtube_token_path=str(row.get("youtube_token_path", "")).strip(),
        )

    def _upload_with_timeout(self, job: QueueJobState, settings: dict) -> str:
        timeout_seconds = float(settings.get("upload_timeout_seconds", 0) or 0)
        if timeout_seconds <= 0:
            return self.uploader.upload(job)
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.uploader.upload, job)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"upload timed out after {timeout_seconds:g} seconds") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _load_channel_configs(self, settings: dict) -> dict[str, dict]:
        if not hasattr(self.sheet_repository, "load_upload_channel_configs"):
            return {}
        try:
            sheet_name = settings.get("channel_config_sheet_name", "Channel Config")
            return self.sheet_repository.load_upload_channel_configs(sheet_name)
        except Exception as exc:
            self.logger.error("channel_config_load_failed", error=str(exc))
            return {}

    def _apply_template(self, template: str, row_value: str, stem: str, channel_cfg: dict) -> str:
        if not template:
            return row_value
        values = {
            "title": row_value or stem,
            "stem": stem,
            "channel_name": channel_cfg.get("channel_name", ""),
            "channel_key": channel_cfg.get("channel_key", ""),
            "account_name": channel_cfg.get("account_name", ""),
        }
        try:
            return template.format(**values)
        except Exception:
            return row_value or stem

    def _merge_channel_defaults(self, row: dict, channel_cfg: dict, settings: dict, source_stem: str) -> dict:
        merged = dict(row)
        if not channel_cfg:
            return merged
        if not str(merged.get("privacyStatus", "")).strip():
            merged["privacyStatus"] = channel_cfg.get("default_privacyStatus", "") or settings.get("youtube_default_privacy", "private")
        if not str(merged.get("categoryId", "")).strip():
            merged["categoryId"] = channel_cfg.get("default_categoryId", "") or settings.get("youtube_default_category_id", "22")
        if not str(merged.get("tags", "")).strip():
            merged["tags"] = channel_cfg.get("tags_default", "")
        merged["channel_key"] = merged.get("channel_key", "") or channel_cfg.get("channel_key", "")
        merged["account_name"] = merged.get("account_name", "") or channel_cfg.get("account_name", "")
        merged["youtube_token_path"] = merged.get("youtube_token_path", "") or channel_cfg.get("youtube_token_path", "")
        title = str(merged.get("title", "")).strip()
        merged["title"] = self._apply_template(channel_cfg.get("title_template", ""), title, source_stem, channel_cfg)
        description = str(merged.get("description", "")).strip()
        merged["description"] = self._apply_template(
            channel_cfg.get("description_template", ""),
            description,
            source_stem,
            channel_cfg,
        )
        return merged

    def process(self, settings: dict) -> list[SheetUploadResult]:
        worksheet_name = settings.get("upload_sheet_name", "Video đã edit")
        pending_status = str(settings.get("upload_status_new", "pending")).strip().lower()
        uploading_status = settings.get("upload_status_uploading", "uploading")
        done_status = settings.get("upload_status_done", "uploaded")
        error_status = settings.get("upload_status_error", "failed")

        results: list[SheetUploadResult] = []
        channel_configs = self._load_channel_configs(settings)
        for row_number, row in self.sheet_repository.load_upload_jobs(worksheet_name):
            if not self._should_process_row(row, settings):
                continue
            video_path = str(row.get("video_path", "")).strip()
            retry_count = self._to_int(row.get("retry_count", 0))
            try:
                channel_key = str(row.get("channel_key", "")).strip()
                channel_cfg = {}
                if channel_key:
                    if channel_key not in channel_configs:
                        raise ValueError(f"channel_key not found or disabled: {channel_key}")
                    channel_cfg = channel_configs[channel_key]
                source_stem = Path(video_path).stem if video_path else ""
                row = self._merge_channel_defaults(row, channel_cfg, settings, source_stem)
                job = self._job_from_row(row_number, row, settings)
                started_at = self._now()
                self.sheet_repository.update_upload_result(
                    worksheet_name,
                    row_number,
                    uploading_status,
                    upload_error="",
                    last_error="",
                    upload_started_at=started_at,
                )
                self.logger.upload(
                    "sheet_upload_started",
                    row_number=row_number,
                    video_path=job.output_path,
                    retry_count=retry_count,
                )
                upload_id = self._upload_with_timeout(job, settings)
                upload_time = self._now()
                self.sheet_repository.update_upload_result(
                    worksheet_name,
                    row_number,
                    done_status,
                    youtube_video_id=upload_id,
                    upload_error="",
                    upload_time=upload_time,
                    last_error="",
                    upload_finished_at=upload_time,
                )
                self.logger.upload(
                    "sheet_upload_finished",
                    row_number=row_number,
                    video_path=job.output_path,
                    youtube_video_id=upload_id,
                )
                results.append(SheetUploadResult(row_number, job.output_path, done_status, upload_id))
            except Exception as exc:
                failed_retry_count = retry_count + 1
                self.sheet_repository.update_upload_result(
                    worksheet_name,
                    row_number,
                    error_status,
                    upload_error=str(exc),
                    retry_count=failed_retry_count,
                    last_error=str(exc),
                    upload_finished_at=self._now(),
                )
                self.logger.error(
                    "sheet_upload_failed",
                    row_number=row_number,
                    video_path=video_path,
                    retry_count=failed_retry_count,
                    error=str(exc),
                )
                results.append(SheetUploadResult(row_number, video_path, error_status, error=str(exc)))
        return results
