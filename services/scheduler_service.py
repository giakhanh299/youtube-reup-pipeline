from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import os
import threading
import time
from typing import Any, Callable

from logs.structured_logger import NullLogger
from repositories.queue_persistence import QueueJobState


@dataclass
class SchedulerTask:
    name: str
    interval_seconds: float
    action: Callable[[], Any]
    retry_interval_seconds: float | None = None
    next_run: float = 0.0
    run_count: int = 0
    error_count: int = 0
    last_result_count: int = 0
    last_error: str = ""


@dataclass(frozen=True)
class SchedulerSnapshot:
    cycles: int
    task_stats: dict[str, dict] = field(default_factory=dict)


class SchedulerDaemon:
    """Simple cooperative scheduler for render/upload cycles."""

    def __init__(
        self,
        tasks: list[SchedulerTask],
        heartbeat_interval_seconds: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
        logger: Any = None,
        stop_event: threading.Event | None = None,
    ):
        self.tasks = tasks
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.sleep = sleep
        self.clock = clock
        self.logger = logger or NullLogger()
        self.stop_event = stop_event or threading.Event()
        self.cycles = 0
        self._next_heartbeat = 0.0

    def stop(self) -> None:
        self.stop_event.set()

    def _result_count(self, result: Any) -> int:
        if result is None:
            return 0
        if isinstance(result, (list, tuple, set, dict)):
            return len(result)
        return 1

    def _run_task(self, task: SchedulerTask, now: float) -> None:
        if task.next_run and now < task.next_run:
            return
        try:
            self.logger.worker("scheduler_task_started", task=task.name)
            result = task.action()
            task.run_count += 1
            task.last_result_count = self._result_count(result)
            task.last_error = ""
            task.next_run = now + max(task.interval_seconds, 0.0)
            self.logger.worker(
                "scheduler_task_finished",
                task=task.name,
                run_count=task.run_count,
                result_count=task.last_result_count,
            )
        except Exception as exc:
            task.error_count += 1
            task.last_error = str(exc)
            retry_interval = task.retry_interval_seconds
            if retry_interval is None:
                retry_interval = task.interval_seconds
            task.next_run = now + max(retry_interval, 0.0)
            self.logger.error(
                "scheduler_task_failed",
                task=task.name,
                error=str(exc),
                error_count=task.error_count,
            )

    def _heartbeat(self, now: float) -> None:
        if self._next_heartbeat and now < self._next_heartbeat:
            return
        self.logger.worker(
            "scheduler_heartbeat",
            cycles=self.cycles,
            task_stats=self.snapshot().task_stats,
        )
        self._next_heartbeat = now + max(self.heartbeat_interval_seconds, 0.0)

    def snapshot(self) -> SchedulerSnapshot:
        return SchedulerSnapshot(
            cycles=self.cycles,
            task_stats={
                task.name: {
                    "run_count": task.run_count,
                    "error_count": task.error_count,
                    "last_result_count": task.last_result_count,
                    "last_error": task.last_error,
                    "next_run": task.next_run,
                }
                for task in self.tasks
            },
        )

    def run(self, max_cycles: int | None = None) -> SchedulerSnapshot:
        self.logger.worker("scheduler_started", task_count=len(self.tasks))
        while not self.stop_event.is_set():
            now = self.clock()
            self._heartbeat(now)
            for task in self.tasks:
                self._run_task(task, now)
            self.cycles += 1
            if max_cycles is not None and self.cycles >= max_cycles:
                break
            self.sleep(1.0)
        self.logger.worker("scheduler_stopped", cycles=self.cycles)
        return self.snapshot()


@dataclass
class QueueSchedulerStats:
    processed_count: int = 0
    uploaded_count: int = 0
    failed_count: int = 0
    recovered_count: int = 0
    skipped_count: int = 0


class SchedulerLock:
    """Local lock file used to prevent duplicate scheduler instances."""

    def __init__(self, lock_path: str | Path):
        self.lock_path = Path(lock_path)
        self.acquired = False

    def acquire(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
            self.acquired = True
            return True
        except FileExistsError:
            return False

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self.acquired = False

    def __enter__(self) -> "SchedulerLock":
        if not self.acquire():
            raise RuntimeError(f"scheduler lock already exists: {self.lock_path}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class QueueAutomationScheduler:
    """Concrete VIDEO_QUEUE render/upload automation loop."""

    def __init__(
        self,
        repository: Any,
        job_processor: Any,
        uploader: Any,
        settings: dict,
        logger: Any = None,
        clock: Callable[[], float] = time.time,
    ):
        self.repository = repository
        self.job_processor = job_processor
        self.uploader = uploader
        self.settings = settings
        self.logger = logger or NullLogger()
        self.clock = clock
        self.stats = QueueSchedulerStats()

    def _log(self, event: str, **fields: Any) -> None:
        scheduler_log = getattr(self.logger, "scheduler", None)
        if callable(scheduler_log):
            scheduler_log(event, **fields)
        else:
            self.logger.worker(event, **fields)

    def recover_stale_processing(self, queue: list[dict]) -> int:
        processing_status = self.settings.get("queue_status_processing", "PROCESSING")
        new_status = self.settings.get("queue_status_new", "NEW")
        stale_after = float(self.settings.get("scheduler_processing_stale_after_seconds", 3600))
        recovered = 0
        now = self.clock()
        for row in queue:
            if str(row.get("status", "")).strip().upper() != processing_status.upper():
                continue
            started_raw = str(row.get("processing_started_at", row.get("upload_started_at", ""))).strip()
            is_stale = True
            if started_raw:
                try:
                    started = datetime.fromisoformat(started_raw.replace("Z", "+00:00")).timestamp()
                    is_stale = now - started >= stale_after
                except Exception:
                    is_stale = True
            if not is_stale:
                continue
            job_id = str(row.get("job_id", "")).strip()
            if job_id:
                self.repository.update_status_by_job_id(job_id, new_status, error="Recovered stale PROCESSING job")
                recovered += 1
        self.stats.recovered_count += recovered
        if recovered:
            self._log("scheduler_recovered_stale_processing", count=recovered)
        return recovered

    def render_cycle(self) -> int:
        _sheet, channels, voices, music_packs, overlay_packs, render_presets, queue = self.repository.load_all()
        self.recover_stale_processing(queue)
        new_status = self.settings.get("queue_status_new", "NEW")
        processing_status = self.settings.get("queue_status_processing", "PROCESSING")
        done_status = self.settings.get("queue_status_done", "READY_UPLOAD")
        error_status = self.settings.get("queue_status_error", "ERROR")
        processed = 0
        for job in queue:
            if str(job.get("status", "")).strip().upper() != new_status.upper():
                continue
            job_id = str(job.get("job_id", "")).strip()
            channel_id = str(job.get("channel_id", "")).strip()
            if not job_id:
                self.stats.skipped_count += 1
                continue
            try:
                if channel_id not in channels:
                    raise KeyError(f"channel_id not found: {channel_id}")
                channel_cfg = self.repository.merge_pack_into_channel(
                    channels[channel_id],
                    music_packs,
                    overlay_packs,
                    render_presets,
                )
                video_path = Path(str(job.get("video_path", "")).strip())
                text_path = Path(str(job.get("text_path", "")).strip())
                self.repository.update_status_by_job_id(job_id, processing_status)
                output = self.job_processor.process_one_video(video_path, text_path, channel_id, channel_cfg, voices, self.settings)
                self.repository.update_status_by_job_id(job_id, done_status, output_path=output, error="")
                processed += 1
                self.stats.processed_count += 1
                self._log("scheduler_render_job_finished", job_id=job_id, channel_id=channel_id, output_path=output)
            except Exception as exc:
                self.repository.update_status_by_job_id(job_id, error_status, error=str(exc))
                self.stats.failed_count += 1
                self.logger.error("scheduler_render_job_failed", job_id=job_id, channel_id=channel_id, error=str(exc))
        return processed

    def upload_cycle(self) -> int:
        _sheet, _channels, _voices, _music_packs, _overlay_packs, _render_presets, queue = self.repository.load_all()
        ready_status = self.settings.get("queue_status_done", "READY_UPLOAD")
        uploaded_status = self.settings.get("queue_status_uploaded", "UPLOADED")
        error_status = self.settings.get("queue_status_error", "ERROR")
        uploaded = 0
        for job in queue:
            if str(job.get("status", "")).strip().upper() != ready_status.upper():
                continue
            if str(job.get("youtube_video_id", "")).strip():
                self.stats.skipped_count += 1
                continue
            job_id = str(job.get("job_id", "")).strip()
            output_path = str(job.get("output_path", "") or job.get("video_path", "")).strip()
            try:
                upload_job = QueueJobState(
                    job_id=job_id,
                    status=ready_status,
                    output_path=output_path,
                    video_path=str(job.get("video_path", "")).strip(),
                    title=str(job.get("title", "")).strip(),
                    description=str(job.get("description", "")).strip(),
                    tags=[item.strip() for item in str(job.get("tags", "")).split(",") if item.strip()],
                    category_id=str(job.get("categoryId", job.get("category_id", ""))).strip(),
                    privacy_status=str(job.get("privacyStatus", job.get("privacy_status", "private"))).strip() or "private",
                    channel_key=str(job.get("channel_key", "")).strip(),
                    account_name=str(job.get("account_name", "")).strip(),
                    youtube_token_path=str(job.get("youtube_token_path", "")).strip(),
                )
                upload_id = self.uploader.upload(upload_job)
                upload_time = datetime.now(timezone.utc).isoformat()
                self.repository.update_status_by_job_id(
                    job_id,
                    uploaded_status,
                    output_path=output_path,
                    error="",
                    youtube_video_id=upload_id,
                    upload_time=upload_time,
                )
                uploaded += 1
                self.stats.uploaded_count += 1
                self._log("scheduler_upload_job_finished", job_id=job_id, youtube_video_id=upload_id)
            except Exception as exc:
                self.repository.update_status_by_job_id(job_id, error_status, output_path=output_path, error=str(exc))
                self.stats.failed_count += 1
                self.logger.error("scheduler_upload_job_failed", job_id=job_id, error=str(exc))
        return uploaded

    def heartbeat(self) -> None:
        self._log(
            "scheduler_heartbeat",
            processed_count=self.stats.processed_count,
            uploaded_count=self.stats.uploaded_count,
            failed_count=self.stats.failed_count,
            recovered_count=self.stats.recovered_count,
            skipped_count=self.stats.skipped_count,
        )
