from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.config_loader import ConfigLoader
from logs.structured_logger import StructuredLogger
from processors.douyin_render_processor import DouyinRenderEngine, DouyinRenderProcessor
from repositories.sheet_repository import SheetRepository
from utils.retry import RetryStrategy


def main() -> int:
    """Render pending Douyin rows from Google Sheet.

    How to run from the repo root:
      python scripts/render_douyin_from_sheet.py

    This script renders only. It does not upload to YouTube.
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
    engine = DouyinRenderEngine(ROOT, logger=logger)
    results = DouyinRenderProcessor(repository, engine, logger=logger).process(settings)
    print(f"Processed render rows: {len(results)}")
    for result in results:
        if result.rendered_video_path:
            print(f"Row {result.row_number}: rendered {result.rendered_video_path}")
        else:
            print(f"Row {result.row_number}: {result.status} {result.error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
