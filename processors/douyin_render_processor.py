from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import subprocess
import time
from typing import Any

from logs.structured_logger import NullLogger
from processors.sheet_client import to_float
from services.voice_registry import resolve_voice_path


@dataclass(frozen=True)
class DouyinRenderResult:
    row_number: int
    source_video_path: str
    status: str
    rendered_video_path: str = ""
    audio_path: str = ""
    error: str = ""
    metadata: dict | None = None


class DouyinRenderEngine:
    """Small FFmpeg-backed Douyin render engine."""

    def __init__(self, root: Path, logger: Any = None):
        self.root = root
        self.logger = logger or NullLogger()

    def resolve_path(self, value: Any) -> str:
        if not value:
            return ""
        path = Path(str(value))
        if path.is_absolute():
            return str(path)
        return str((self.root / path).resolve())

    def validate_source(self, source_video_path: str, allowed_exts: list[str]) -> Path:
        source = Path(self.resolve_path(source_video_path))
        if not source.exists():
            raise FileNotFoundError(f"source_video_path not found: {source}")
        if not source.is_file():
            raise ValueError(f"source_video_path is not a file: {source}")
        if source.suffix.lower() not in {ext.lower() for ext in allowed_exts}:
            raise ValueError(f"unsupported source video extension: {source.suffix}")
        return source

    def extract_metadata(self, source_video: Path) -> dict:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(source_video),
        ]
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            return json.loads(result.stdout or "{}")
        except Exception as exc:
            self.logger.render("douyin_metadata_unavailable", video=str(source_video), error=str(exc))
            return {}

    def extract_audio(self, source_video: Path, temp_dir: Path) -> Path:
        temp_dir.mkdir(parents=True, exist_ok=True)
        audio_file = temp_dir / f"{source_video.stem}_{int(time.time())}.m4a"
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source_video),
            "-vn",
            "-c:a",
            "aac",
            str(audio_file),
        ]
        subprocess.run(cmd, check=True)
        return audio_file

    def create_tts_audio(self, row: dict, settings: dict, temp_dir: Path) -> Path | None:
        text = str(
            row.get("script_text")
            or row.get("tts_text")
            or row.get("text")
            or row.get("title_vi")
            or row.get("title")
            or ""
        ).strip()
        if not text:
            return None
        from services.tts_service import TTSService

        temp_dir.mkdir(parents=True, exist_ok=True)
        output_audio_raw = str(row.get("output_audio_path") or row.get("voice_output_path") or "").strip()
        audio_file = Path(self.resolve_path(output_audio_raw)) if output_audio_raw else temp_dir / f"tts_{int(time.time())}.wav"
        ref_audio_path = self.resolve_path(row.get("ref_audio_path", ""))
        voice_name = str(
            row.get("voice_name")
            or row.get("voice")
            or row.get("voice_file")
            or row.get("reference_voice")
            or ""
        ).strip()
        default_voice_name = str(settings.get("default_voice_name", "")).strip()
        if voice_name or default_voice_name:
            voices_dir = Path(self.resolve_path(settings.get("voices_dir", "runtime/voices")))
            ref_audio_path = str(resolve_voice_path(voice_name, voices_dir, default_voice_name))
        voice_cfg = {
            "engine": row.get("voice_engine") or row.get("tts_engine") or settings.get("voice_engine", "omnivoice_local"),
            "language": row.get("language", settings.get("omnivoice_default_language", "vi")),
            "ref_audio_path": ref_audio_path,
            "reference_audio": ref_audio_path,
            "voice_path": ref_audio_path,
            "ref_text": row.get("ref_text", ""),
            "speaking_rate": to_float(row.get("voice_speed"), 1.0),
            "speed": to_float(row.get("speed", row.get("voice_speed")), 1.0),
            "pitch": to_float(row.get("voice_pitch"), 0.0),
            "active": True,
        }
        engine = str(voice_cfg["engine"]).strip().lower()
        if engine in {"omnivoice", "omnivoice_local", "local_omnivoice"}:
            missing = [name for name in ("ref_audio_path", "ref_text") if not str(voice_cfg.get(name, "")).strip()]
            if missing:
                channel_id = str(row.get("channel_id", "")).strip()
                row_label = f" for channel_id={channel_id}" if channel_id else ""
                raise ValueError(f"Missing OmniVoice field(s){row_label}: {', '.join(missing)}")
        TTSService(settings=settings).create_voice(text, audio_file, voice_cfg, settings.get("google_key_dir", ""))
        return audio_file

    def render_video(self, source_video: Path, audio_path: Path, output_video: Path) -> None:
        output_video.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source_video),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(output_video),
        ]
        subprocess.run(cmd, check=True)


class DouyinRenderProcessor:
    """Processes Douyin render rows from Google Sheet."""

    def __init__(self, sheet_repository: Any, engine: DouyinRenderEngine, logger: Any = None):
        self.sheet_repository = sheet_repository
        self.engine = engine
        self.logger = logger or NullLogger()

    def _should_process_row(self, row: dict, settings: dict) -> bool:
        status = str(row.get("render_status", "")).strip().lower()
        pending = str(settings.get("render_status_new", "pending")).strip().lower()
        ready = str(settings.get("render_status_done", "ready")).strip().lower()
        if status == ready:
            return False
        return not status or status == pending

    def _output_path_for(self, source_video: Path, row: dict, settings: dict) -> Path:
        explicit = str(row.get("rendered_video_path", "")).strip()
        if explicit:
            return Path(self.engine.resolve_path(explicit))
        output_dir = Path(self.engine.resolve_path(settings.get("render_output_dir", "runtime/rendered")))
        return output_dir / f"{source_video.stem}_rendered.mp4"

    def process(self, settings: dict) -> list[DouyinRenderResult]:
        worksheet_name = settings.get("render_sheet_name", settings.get("upload_sheet_name", "Video da edit"))
        allowed_exts = settings.get("render_allowed_exts", settings.get("video_exts", [".mp4", ".mkv", ".avi", ".mov"]))
        temp_dir = Path(self.engine.resolve_path(settings.get("render_temp_dir", "runtime/temp/douyin_render")))
        rendering_status = settings.get("render_status_processing", "rendering")
        done_status = settings.get("render_status_done", "ready")
        error_status = settings.get("render_status_error", "failed")

        results: list[DouyinRenderResult] = []
        for row_number, row in self.sheet_repository.load_render_jobs(worksheet_name):
            if not self._should_process_row(row, settings):
                continue
            source_raw = str(row.get("source_video_path", row.get("video_path", ""))).strip()
            try:
                source_video = self.engine.validate_source(source_raw, allowed_exts)
                metadata = self.engine.extract_metadata(source_video)
                self.sheet_repository.update_render_result(worksheet_name, row_number, rendering_status)
                tts_audio = self.engine.create_tts_audio(row, settings, temp_dir)
                extracted_audio = None
                audio_path = tts_audio
                if audio_path is None:
                    existing_audio = str(row.get("audio_path", "")).strip()
                    audio_path = Path(self.engine.resolve_path(existing_audio)) if existing_audio else None
                if audio_path is None or not audio_path.exists():
                    extracted_audio = self.engine.extract_audio(source_video, temp_dir)
                    audio_path = extracted_audio
                output_video = self._output_path_for(source_video, row, settings)
                self.engine.render_video(source_video, audio_path, output_video)
                self.sheet_repository.update_render_result(
                    worksheet_name,
                    row_number,
                    done_status,
                    audio_path=str(audio_path),
                    rendered_video_path=str(output_video),
                    render_error="",
                )
                self.logger.render(
                    "douyin_render_finished",
                    row_number=row_number,
                    source_video_path=str(source_video),
                    rendered_video_path=str(output_video),
                )
                results.append(
                    DouyinRenderResult(row_number, str(source_video), done_status, str(output_video), str(audio_path), metadata=metadata)
                )
                for temp_audio in (tts_audio, extracted_audio):
                    if temp_audio and temp_audio.exists():
                        try:
                            temp_audio.unlink()
                        except OSError:
                            pass
            except Exception as exc:
                self.sheet_repository.update_render_result(
                    worksheet_name,
                    row_number,
                    error_status,
                    render_error=str(exc),
                )
                self.logger.error("douyin_render_failed", row_number=row_number, source_video_path=source_raw, error=str(exc))
                results.append(DouyinRenderResult(row_number, source_raw, error_status, error=str(exc)))
        return results
