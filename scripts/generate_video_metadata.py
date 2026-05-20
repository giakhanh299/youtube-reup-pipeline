from __future__ import annotations

from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.config_loader import ConfigLoader
from logs.structured_logger import StructuredLogger
from repositories.sheet_repository import SheetRepository
from services.metadata_service import MetadataService
from utils.retry import RetryStrategy


def needs_metadata(row: dict, force: bool = False) -> bool:
    if force:
        return True
    return not (
        str(row.get("final_title", "")).strip()
        and str(row.get("final_description", "")).strip()
        and str(row.get("tags", "")).strip()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate VIDEO_QUEUE metadata.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = ConfigLoader(ROOT).load_settings()
    logger = StructuredLogger(ROOT / settings.get("log_dir", "runtime/logs"))
    retry_strategy = RetryStrategy(
        max_attempts=int(settings.get("retry_max_attempts", 3)),
        base_delay=float(settings.get("retry_base_delay", 1.0)),
        max_delay=float(settings.get("retry_max_delay", 30.0)),
        logger=logger,
    )
    repository = SheetRepository.from_settings(settings, ROOT, retry_strategy=retry_strategy, logger=logger)
    _sheet, channels, _voices, _music_packs, _overlay_packs, _render_presets, queue = repository.load_all()
    service = MetadataService()
    processed = 0
    for row in queue:
        if args.limit and processed >= args.limit:
            break
        if not needs_metadata(row, args.force):
            continue
        job_id = str(row.get("job_id", "")).strip()
        if not job_id:
            continue
        channel_id = str(row.get("channel_id", "")).strip()
        updates = service.generate(row, channels.get(channel_id, {}), force=args.force)
        if not updates:
            continue
        processed += 1
        if args.dry_run:
            print(f"DRY RUN {job_id}: {updates}")
            continue
        repository.update_video_queue_fields_by_job_id(job_id, updates)
        print(f"OK metadata updated: {job_id}")
    print(f"OK processed metadata rows: {processed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
