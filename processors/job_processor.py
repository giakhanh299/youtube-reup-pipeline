from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from logs.structured_logger import NullLogger
from services.render_service import RenderService
from services.text_service import TextService
from services.tts_service import TTSService
from services.voice_registry import resolve_voice_path


def safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in name).strip()


def _resolve_path(root: Path, value: Any) -> Path:
    path = Path(str(value))
    if path.is_absolute():
        return path
    return (root / path).resolve()


def _first_text(row: dict | None, keys: tuple[str, ...]) -> str:
    if not row:
        return ""
    for key in keys:
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def _resolve_row_voice_path(root: Path, job_row: dict | None, settings: dict) -> str:
    voice_name = _first_text(job_row, ("voice_name", "voice", "voice_file", "reference_voice"))
    default_voice_name = str(settings.get("default_voice_name", "")).strip()
    if not voice_name and not default_voice_name:
        return ""
    voices_dir = settings.get("voices_dir", "runtime/voices")
    voices_root = _resolve_path(root, voices_dir)
    return str(resolve_voice_path(voice_name, voices_root, default_voice_name))


class VideoJobProcessor:
    """Processes one video using existing TTS and render behavior."""

    def __init__(
        self,
        root: Path,
        text_service: TextService | None = None,
        tts_service: TTSService | None = None,
        render_service: RenderService | None = None,
        logger: Any = None,
    ):
        self.root = root
        self.text_service = text_service or TextService()
        self.tts_service = tts_service or TTSService()
        self.render_service = render_service or RenderService()
        self.logger = logger or NullLogger()

    def process_one_video(
        self,
        video: Path,
        text_file: Path | None,
        channel_id: str,
        channel_cfg: dict,
        voices: dict,
        settings: dict,
        job_row: dict | None = None,
    ) -> str:
        temp_dir = self.root / settings.get("temp_dir", "runtime/temp") / channel_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_folder_raw = str(channel_cfg.get("output_folder", "")).strip()
        if not output_folder_raw:
            raise ValueError(f"Missing output_folder for channel_id={channel_id}")
        output_folder = _resolve_path(self.root, output_folder_raw)
        output_folder.mkdir(parents=True, exist_ok=True)
        job_name = safe_name(video.stem)
        voice_file = temp_dir / f"{job_name}_{int(time.time())}.wav"
        output_file = output_folder / f"{channel_id}_{job_name}.mp4"

        try:
            print(f"> [{channel_id}] {video.name}")
            self.logger.app("job_started", channel_id=channel_id, video=str(video))
            text = _first_text(job_row, ("script_text", "tts_text", "text", "title_vi", "title", "title_original"))
            if text:
                print("  -> Text: Google Sheet row")
            elif text_file:
                print(f"  -> Text: {text_file.name}")
                text = self.text_service.to_plain_text(text_file)
            if not text:
                raise ValueError("Text empty")
            voice_id = channel_cfg["voice_id"]
            if voice_id not in voices:
                raise KeyError(f"Voice not found in VOICE_CONFIG: {voice_id}")
            voice_cfg = dict(voices[voice_id])
            if not voice_cfg.get("active", True):
                raise ValueError(f"Voice is inactive: {voice_id}")
            if job_row:
                voice_cfg.update(
                    {
                        "engine": job_row.get("voice_engine") or job_row.get("tts_engine") or voice_cfg.get("engine"),
                        "tts_engine": job_row.get("tts_engine") or job_row.get("voice_engine") or voice_cfg.get("tts_engine"),
                        "language": job_row.get("language") or voice_cfg.get("language"),
                        "ref_audio_path": job_row.get("ref_audio_path") or voice_cfg.get("ref_audio_path"),
                        "reference_audio": job_row.get("reference_audio") or voice_cfg.get("reference_audio"),
                        "voice_path": job_row.get("voice_path") or voice_cfg.get("voice_path"),
                        "ref_text": job_row.get("ref_text") or voice_cfg.get("ref_text"),
                        "speed": job_row.get("speed") or job_row.get("voice_speed") or voice_cfg.get("speed"),
                        "pitch": job_row.get("pitch") or job_row.get("voice_pitch") or voice_cfg.get("pitch"),
                    }
                )
            selected_voice_path = _resolve_row_voice_path(self.root, job_row, settings)
            if selected_voice_path:
                voice_cfg["ref_audio_path"] = selected_voice_path
                voice_cfg["reference_audio"] = selected_voice_path
                voice_cfg["voice_path"] = selected_voice_path
            engine = str(
                voice_cfg.get("tts_engine") or voice_cfg.get("engine") or settings.get("voice_engine", "omnivoice_local")
            ).strip().lower()
            voice_cfg.setdefault("engine", engine)
            voice_cfg.setdefault("tts_engine", engine)
            voice_cfg.setdefault("omnivoice_model_path", settings.get("omnivoice_model_path", ""))
            voice_cfg.setdefault("omnivoice_model_name", settings.get("omnivoice_model_name", "k2-fsa/OmniVoice"))
            voice_cfg.setdefault("omnivoice_device", settings.get("omnivoice_device", "auto"))
            voice_cfg.setdefault("omnivoice_local_files_only", settings.get("omnivoice_local_files_only", True))
            voice_suffix = ".wav" if engine in {"omnivoice", "omnivoice_local", "local_omnivoice"} else ".mp3"
            explicit_voice_output = _first_text(job_row, ("voice_output_path", "output_audio_path"))
            voice_file = _resolve_path(self.root, explicit_voice_output) if explicit_voice_output else voice_file.with_suffix(voice_suffix)
            if engine in {"omnivoice", "omnivoice_local", "local_omnivoice"}:
                missing = [name for name in ("ref_audio_path", "ref_text") if not str(voice_cfg.get(name, "")).strip()]
                if missing:
                    raise ValueError(f"Missing OmniVoice field(s) for channel_id={channel_id}: {', '.join(missing)}")
            print(f"  -> Create voice: {voice_id}")
            self.tts_service.create_voice(text, voice_file, voice_cfg, settings.get("google_key_dir", ""))
            print("  -> Render video from Google Sheet config")
            self.logger.render("render_started", channel_id=channel_id, video=str(video), output=str(output_file))
            self.render_service.render_video(video, voice_file, output_file, channel_cfg)
            print(f"  OK: {output_file}")
            self.logger.render("render_finished", channel_id=channel_id, video=str(video), output=str(output_file))
            return str(output_file)
        finally:
            try:
                if not _first_text(job_row, ("voice_output_path", "output_audio_path")) and voice_file.exists():
                    voice_file.unlink()
            except OSError:
                pass
