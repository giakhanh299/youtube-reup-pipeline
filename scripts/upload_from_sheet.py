from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.config_loader import ConfigLoader
from integrations.youtube.youtube_api_uploader import YouTubeApiUploader
from logs.structured_logger import StructuredLogger
from processors.sheet_upload_processor import SheetUploadProcessor
from repositories.sheet_repository import SheetRepository
from utils.retry import RetryStrategy


def main() -> int:
    """Upload pending rows from the configured upload sheet.

    How to run from the repo root:
      python scripts/upload_from_sheet.py

    Reads the sheet tab configured by upload_sheet_name, defaulting to
    "Video đã edit". This does not change pipeline.py rendering behavior.
    """

    settings = ConfigLoader(ROOT).load_settings()
    logger = StructuredLogger(ROOT / settings.get("log_dir", "runtime/logs"))
    retry_strategy = RetryStrategy(
        max_attempts=int(settings.get("retry_max_attempts", 3)),
        base_delay=float(settings.get("retry_base_delay", 1.0)),
        max_delay=float(settings.get("retry_max_delay", 30.0)),
        logger=logger,
    )
    repository = SheetRepository.from_settings(settings, ROOT, retry_strategy=retry_strategy, logger=logger)
    uploader = YouTubeApiUploader.from_settings(settings, retry_strategy=retry_strategy, logger=logger)
    results = SheetUploadProcessor(repository, uploader, logger=logger).process(settings)

    print(f"Processed upload rows: {len(results)}")
    for result in results:
        if result.youtube_video_id:
            print(f"Row {result.row_number}: uploaded {result.youtube_video_id}")
        else:
            print(f"Row {result.row_number}: {result.status} {result.error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
