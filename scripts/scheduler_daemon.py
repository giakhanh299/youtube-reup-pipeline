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
from processors.douyin_render_processor import DouyinRenderEngine, DouyinRenderProcessor
from processors.sheet_upload_processor import SheetUploadProcessor
from repositories.sheet_repository import SheetRepository
from services.scheduler_service import SchedulerDaemon, SchedulerTask
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
    render_processor = DouyinRenderProcessor(repository, DouyinRenderEngine(ROOT, logger=logger), logger=logger)
    upload_processor = SheetUploadProcessor(repository, MultiAccountUploader(settings, logger=logger), logger=logger)

    stop_event = threading.Event()

    def request_stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    tasks = [
        SchedulerTask(
            "douyin_render",
            float(settings.get("scheduler_processing_interval_seconds", 300)),
            lambda: render_processor.process(settings),
            retry_interval_seconds=float(settings.get("scheduler_retry_interval_seconds", 60)),
        ),
        SchedulerTask(
            "youtube_upload",
            float(settings.get("scheduler_upload_interval_seconds", 300)),
            lambda: upload_processor.process(settings),
            retry_interval_seconds=float(settings.get("scheduler_retry_interval_seconds", 60)),
        ),
    ]
    scheduler = SchedulerDaemon(
        tasks,
        heartbeat_interval_seconds=float(settings.get("scheduler_heartbeat_interval_seconds", 60)),
        logger=logger,
        stop_event=stop_event,
    )
    scheduler.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
