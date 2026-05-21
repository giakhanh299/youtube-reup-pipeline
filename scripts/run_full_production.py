from __future__ import annotations

from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.config_loader import ConfigLoader
from logs.structured_logger import StructuredLogger
from processors.job_processor import VideoJobProcessor
from repositories.sheet_repository import SheetRepository
from services.channel_sheet_registry import ChannelSheetRegistry
from services.render_service import RenderService
from services.tts_service import TTSService
from utils.retry import RetryStrategy
from workers.channel_worker import ChannelWorker
from workers.multi_account_upload_worker import MultiAccountUploader


def main() -> int:
    parser = argparse.ArgumentParser(description="Run sheet-controlled production processing for many channels.")
    parser.add_argument("--source", choices=["google_sheet"], default="google_sheet")
    parser.add_argument("--max-channels", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true", help="Render only; do not upload.")
    args = parser.parse_args()

    settings = ConfigLoader(ROOT).load_settings()
    settings["voice_engine"] = "omnivoice_local"
    logger = StructuredLogger(ROOT / settings.get("log_dir", "runtime/logs"))
    retry_strategy = RetryStrategy(
        max_attempts=int(settings.get("retry_max_attempts", 3)),
        base_delay=float(settings.get("retry_base_delay", 1.0)),
        max_delay=float(settings.get("retry_max_delay", 30.0)),
        logger=logger,
    )
    repository = SheetRepository.from_settings(settings, ROOT, retry_strategy=retry_strategy, logger=logger)
    registry = ChannelSheetRegistry(repository, settings, ROOT)
    job_processor = VideoJobProcessor(
        ROOT,
        tts_service=TTSService(retry_strategy=retry_strategy, logger=logger, settings=settings),
        render_service=RenderService(retry_strategy=retry_strategy, logger=logger),
        logger=logger,
    )
    uploader = None if args.dry_run else MultiAccountUploader(settings, logger=logger)
    worker = ChannelWorker(registry, job_processor, uploader, settings, logger=logger)
    results = worker.process(max_channels=args.max_channels)
    for result in results:
        print(f"{result.status} {result.channel_id} {result.video_path} {result.output_path} {result.youtube_video_id} {result.error}".strip())
    return 1 if any(result.status == "error" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
