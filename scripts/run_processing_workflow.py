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
from services.active_channel_state import ActiveChannelStateStore
from services.processing_workflow import ProcessingWorkflow, ProcessingWorkflowError
from utils.retry import RetryStrategy


def main() -> int:
    parser = argparse.ArgumentParser(description="Run active-channel subtitle/transcription processing workflow.")
    parser.add_argument("--source-dir", default="", help="Override legacy source folder for this run.")
    parser.add_argument("--processing-dir", default="", help="Override legacy processing folder for this run.")
    args = parser.parse_args()

    settings = ConfigLoader(ROOT).load_settings()
    if args.source_dir:
        settings["processing_source_dir"] = args.source_dir
    if args.processing_dir:
        settings["processing_work_dir"] = args.processing_dir

    logger = StructuredLogger(ROOT / settings.get("log_dir", "runtime/logs"))
    active_channel = ActiveChannelStateStore(ROOT, settings, logger=logger).load()
    if active_channel is None:
        print("ERROR no active channel selected. Run: python scripts\\run_full_production.py --channel-id <channel_id>", file=sys.stderr)
        return 1

    retry_strategy = RetryStrategy(
        max_attempts=int(settings.get("retry_max_attempts", 3)),
        base_delay=float(settings.get("retry_base_delay", 1.0)),
        max_delay=float(settings.get("retry_max_delay", 30.0)),
    )
    repository = SheetRepository.from_settings(settings, ROOT, retry_strategy=retry_strategy, logger=logger)
    _sheet, channels, voices, music_packs, overlay_packs, render_presets, _queue = repository.load_all()
    if active_channel.channel_id not in channels:
        print(f"ERROR active channel not found in CHANNEL_CONFIG: {active_channel.channel_id}", file=sys.stderr)
        return 1
    channel_cfg = repository.merge_pack_into_channel(channels[active_channel.channel_id], music_packs, overlay_packs, render_presets)

    try:
        result = ProcessingWorkflow(
            ROOT,
            settings,
            active_channel,
            sheet_repository=repository,
            channel_cfg=channel_cfg,
            voices=voices,
            logger=logger,
        ).run()
    except ProcessingWorkflowError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR processing workflow failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"OK channel={result.active_channel_id} subtitles={result.subtitles_created} "
        f"translations={result.subtitles_translated} voice_tracks={result.voice_tracks_created} renders={result.videos_rendered}"
    )
    print(f"OK source={result.source_dir}")
    print(f"OK processing={result.processing_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
