from __future__ import annotations

from pathlib import Path
import signal
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.config_loader import ConfigLoader
from logs.structured_logger import StructuredLogger
from processors.job_processor import VideoJobProcessor
from repositories.sheet_repository import SheetRepository
from services.render_service import RenderService
from services.scheduler_service import QueueAutomationScheduler, SchedulerDaemon, SchedulerLock, SchedulerTask
from services.tts_service import TTSService
from utils.retry import RetryStrategy
from workers.multi_account_upload_worker import MultiAccountUploader


def main() -> int:
    settings = ConfigLoader(ROOT).load_settings()
    logger = StructuredLogger(ROOT / settings.get("log_dir", "runtime/logs"))
    retry_strategy = RetryStrategy(
        max_attempts=int(settings.get("retry_max_attempts", 3)),
        base_delay=float(settings.get("retry_base_delay", 1.0)),
        max_delay=float(settings.get("retry_max_delay", 30.0)),
        logger=logger,
    )
    repository = SheetRepository.from_settings(settings, ROOT, retry_strategy=retry_strategy, logger=logger)
    job_processor = VideoJobProcessor(
        ROOT,
        tts_service=TTSService(retry_strategy=retry_strategy, logger=logger),
        render_service=RenderService(retry_strategy=retry_strategy, logger=logger),
        logger=logger,
    )
    queue_scheduler = QueueAutomationScheduler(
        repository,
        job_processor,
        MultiAccountUploader(settings, logger=logger),
        settings,
        logger=logger,
    )
    stop_event = threading.Event()

    def request_stop(_signum, _frame) -> None:
        logger.scheduler("scheduler_shutdown_requested")
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    tasks = [
        SchedulerTask(
            "video_queue_render",
            float(settings.get("scheduler_render_interval_seconds", settings.get("scheduler_processing_interval_seconds", 300))),
            queue_scheduler.render_cycle,
            retry_interval_seconds=float(settings.get("scheduler_retry_interval_seconds", 60)),
        ),
        SchedulerTask(
            "video_queue_upload",
            float(settings.get("scheduler_upload_interval_seconds", 300)),
            queue_scheduler.upload_cycle,
            retry_interval_seconds=float(settings.get("scheduler_retry_interval_seconds", 60)),
        ),
        SchedulerTask(
            "scheduler_heartbeat",
            float(settings.get("scheduler_heartbeat_interval_seconds", 60)),
            lambda: queue_scheduler.heartbeat() or [],
            retry_interval_seconds=float(settings.get("scheduler_retry_interval_seconds", 60)),
        ),
    ]
    lock_path = ROOT / settings.get("scheduler_lock_path", "runtime/state/scheduler.lock")
    try:
        with SchedulerLock(lock_path):
            logger.scheduler("scheduler_started", lock_path=str(lock_path))
            SchedulerDaemon(
                tasks,
                heartbeat_interval_seconds=float(settings.get("scheduler_heartbeat_interval_seconds", 60)),
                logger=logger,
                stop_event=stop_event,
            ).run()
            logger.scheduler("scheduler_stopped")
    except RuntimeError as exc:
        logger.error("scheduler_lock_failed", error=str(exc))
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
