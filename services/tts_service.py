from __future__ import annotations

from pathlib import Path
from typing import Any

from processors.sheet_client import to_bool
from processors.tts_engine import create_voice
from services.omnivoice_local_service import OmniVoiceLocalService
from utils.retry import RetryStrategy


class TTSService:
    """TTS service wrapper.

    Google TTS is deprecated and only used when explicitly requested. The
    default runtime voice engine is local OmniVoice.
    """

    def __init__(self, retry_strategy: RetryStrategy | None = None, logger: Any = None, settings: dict | None = None):
        self.retry_strategy = retry_strategy
        self.logger = logger
        self.settings = settings or {}

    def create_voice(self, text: str, output_file: Path, voice_cfg: dict, google_key_dir: str = "") -> None:
        engine = str(
            voice_cfg.get("tts_engine")
            or voice_cfg.get("engine")
            or self.settings.get("voice_engine")
            or "omnivoice_local"
        ).strip().lower()
        if engine in {"omnivoice", "omnivoice_local", "local_omnivoice"}:
            operation = lambda: OmniVoiceLocalService(
                model_name=voice_cfg.get("omnivoice_model_name") or self.settings.get("omnivoice_model_name", "k2-fsa/OmniVoice"),
                local_files_only=to_bool(
                    voice_cfg.get("omnivoice_local_files_only", self.settings.get("omnivoice_local_files_only")),
                    True,
                ),
                device=voice_cfg.get("omnivoice_device") or self.settings.get("omnivoice_device", "auto"),
            ).synthesize(
                text,
                voice_cfg.get("ref_audio_path") or voice_cfg.get("reference_audio") or voice_cfg.get("voice_path") or "",
                voice_cfg.get("ref_text", ""),
                output_file,
                language=voice_cfg.get("language") or voice_cfg.get("language_code") or self.settings.get("omnivoice_default_language", "vi"),
                speed=voice_cfg.get("speed", voice_cfg.get("speaking_rate", 1.0)),
                pitch=voice_cfg.get("pitch", 0.0),
            )
            if self.retry_strategy:
                self.retry_strategy.run(operation, "tts_omnivoice_create_voice", "tts")
                return
            operation()
            return

        if self.retry_strategy:
            self.retry_strategy.run(
                lambda: create_voice(text, output_file, voice_cfg, google_key_dir),
                "tts_create_voice",
                "tts",
            )
            return
        create_voice(text, output_file, voice_cfg, google_key_dir)
