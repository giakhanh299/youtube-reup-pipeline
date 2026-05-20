from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from configs.config_loader import ConfigLoader
from logs.structured_logger import StructuredLogger
from processors.folder_processor import FolderProcessor
from processors.job_processor import VideoJobProcessor, safe_name as _safe_name
from processors.queue_processor import QueueProcessor
from processors.sheet_client import SheetConfig
from repositories.queue_persistence import JsonQueuePersistence
from repositories.sheet_repository import SheetRepository
from services.render_service import RenderService
from services.tts_service import TTSService
from utils.retry import RetryStrategy

ROOT = Path(__file__).resolve().parent


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_name(name: str) -> str:
    return _safe_name(name)


def parse_list(value: Any) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in str(value).split(",") if x.strip()]


def _offline_repository() -> SheetRepository:
    return SheetRepository(SheetConfig("", ""), ROOT)


def resolve_path(value: Any) -> str:
    return _offline_repository().resolve_path(value)


def normalize_channel(row: dict) -> dict:
    return _offline_repository().normalize_channel(row)


def normalize_voice(row: dict) -> dict:
    return _offline_repository().normalize_voice(row)


def merge_pack_into_channel(channel: dict, music_packs: dict, overlay_packs: dict, render_presets: dict) -> dict:
    return _offline_repository().merge_pack_into_channel(channel, music_packs, overlay_packs, render_presets)


def load_sheet_data(settings: dict):
    return SheetRepository.from_settings(settings, ROOT).load_all()


def build_runtime_dependencies(settings: dict) -> tuple[StructuredLogger, RetryStrategy]:
    log_dir = ROOT / settings.get("log_dir", "runtime/logs")
    logger = StructuredLogger(log_dir)
    retry_strategy = RetryStrategy(
        max_attempts=int(settings.get("retry_max_attempts", 3)),
        base_delay=float(settings.get("retry_base_delay", 1.0)),
        max_delay=float(settings.get("retry_max_delay", 30.0)),
        logger=logger,
    )
    return logger, retry_strategy


def process_one_video(
    video: Path,
    text_file: Path,
    channel_id: str,
    channel_cfg: dict,
    voices: dict,
    settings: dict,
) -> str:
    return VideoJobProcessor(ROOT).process_one_video(video, text_file, channel_id, channel_cfg, voices, settings)


def process_folder_mode(
    channels: dict,
    voices: dict,
    music_packs: dict,
    overlay_packs: dict,
    render_presets: dict,
    settings: dict,
) -> None:
    repository = _offline_repository()
    FolderProcessor(repository, VideoJobProcessor(ROOT)).process(
        channels,
        voices,
        music_packs,
        overlay_packs,
        render_presets,
        settings,
    )


def process_queue_mode(
    sheet: SheetConfig,
    channels: dict,
    voices: dict,
    music_packs: dict,
    overlay_packs: dict,
    render_presets: dict,
    queue: list[dict],
    settings: dict,
) -> None:
    repository = SheetRepository(sheet, ROOT)
    QueueProcessor(repository, VideoJobProcessor(ROOT)).process(
        channels,
        voices,
        music_packs,
        overlay_packs,
        render_presets,
        queue,
        settings,
    )


def main() -> None:
    settings = ConfigLoader(ROOT).load_settings()
    logger, retry_strategy = build_runtime_dependencies(settings)
    repository = SheetRepository.from_settings(settings, ROOT, retry_strategy=retry_strategy, logger=logger)
    _sheet, channels, voices, music_packs, overlay_packs, render_presets, queue = repository.load_all()
    job_processor = VideoJobProcessor(
        ROOT,
        tts_service=TTSService(retry_strategy=retry_strategy, logger=logger, settings=settings),
        render_service=RenderService(retry_strategy=retry_strategy, logger=logger),
        logger=logger,
    )

    if settings.get("process_queue_only", False):
        QueueProcessor(
            repository,
            job_processor,
            logger=logger,
            queue_persistence=JsonQueuePersistence(ROOT / settings.get("queue_state_dir", "runtime/state/queue")),
        ).process(
            channels,
            voices,
            music_packs,
            overlay_packs,
            render_presets,
            queue,
            settings,
        )
    else:
        FolderProcessor(repository, job_processor, logger=logger).process(
            channels,
            voices,
            music_packs,
            overlay_packs,
            render_presets,
            settings,
        )


if __name__ == "__main__":
    main()
