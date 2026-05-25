from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import os
import re
import shutil
import sys
import time
import unicodedata
from typing import Any, Protocol

from processors.sheet_client import to_bool
from services.active_channel_state import ActiveChannelState
from services.render_service import RenderService
from services.tts_service import TTSService
from services.voice_registry import resolve_voice_path


LEGACY_SOURCE_DIR = r"G:\My Drive\Video Doujin\VIDEO IN PUT GIAKHANH CHANEL"
LEGACY_PROCESSING_DIR = r"G:\My Drive\Video Doujin\VIDEO IN PUT GIAKHANH CHANEL\DA_XU_LY"


class ProcessingWorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessingWorkflowResult:
    active_channel_id: str
    active_channel_name: str
    source_dir: str
    processing_dir: str
    subtitles_created: int
    subtitles_translated: int
    voice_tracks_created: int = 0
    videos_rendered: int = 0


@dataclass(frozen=True)
class SubtitleSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class SubtitleItem:
    id: str
    time: str
    text: str


class Transcriber(Protocol):
    def transcribe(self, video_path: Path) -> list[SubtitleSegment]:
        raise NotImplementedError


class SubtitleTranslator(Protocol):
    def translate_batch(self, batch: list[SubtitleItem]) -> dict[str, str]:
        raise NotImplementedError


def _setup_legacy_gpu_paths() -> None:
    user_site = os.path.expanduser(r"~\AppData\Roaming\Python\Python310\site-packages")
    system_site = r"C:\Program Files\Python310\Lib\site-packages"
    for path in (user_site, system_site):
        if path not in sys.path:
            sys.path.insert(0, path)
        for folder in ("nvidia_cublas_cu12", "nvidia_cudnn_cu12", "nvidia_cuda_nvrtc_cu12"):
            dll_path = os.path.join(path, folder, "lib")
            if os.path.exists(dll_path):
                if hasattr(os, "add_dll_directory"):
                    os.add_dll_directory(dll_path)
                os.environ["PATH"] = dll_path + os.pathsep + os.environ["PATH"]


class FasterWhisperTranscriber:
    def __init__(self, model_size: str = "medium"):
        os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
        _setup_legacy_gpu_paths()
        from faster_whisper import WhisperModel

        try:
            self.model = WhisperModel(model_size, device="cuda", device_index=0, compute_type="float16")
        except Exception:
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe(self, video_path: Path) -> list[SubtitleSegment]:
        segments, _info = self.model.transcribe(str(video_path), beam_size=5)
        return [SubtitleSegment(float(seg.start), float(seg.end), str(seg.text).strip()) for seg in segments]


class OpenAISubtitleTranslator:
    def __init__(self, api_key: str, base_url: str, model_name: str, currency_rate: int = 4000):
        if not api_key:
            raise ProcessingWorkflowError("Missing subtitle translation API key")
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key.strip(), base_url=base_url)
        self.model_name = model_name
        self.currency_rate = currency_rate

    def translate_batch(self, batch: list[SubtitleItem]) -> dict[str, str]:
        prompt_text = "\n".join([f"[{item.id}] {item.text}" for item in batch])
        messages = [
            {"role": "system", "content": "You are a professional subtitle translator. Translate to Vietnamese. Keep format [ID] translation."},
            {"role": "user", "content": f"Dich muot ma, tu nhien:\n{prompt_text}"},
        ]
        response = self.client.chat.completions.create(model=self.model_name, messages=messages, temperature=0.3)
        result_text = response.choices[0].message.content
        translated: dict[str, str] = {}
        for line_id, content in re.findall(r"\[(\d+)\][:\s]*(.*)", result_text):
            translated[line_id] = convert_to_million_vnd(clean_ai_garbage(content), self.currency_rate)
        return translated


def _first_config_value(settings: dict, setting_key: str, env_keys: tuple[str, ...]) -> str:
    value = str(settings.get(setting_key) or "").strip()
    if value:
        return value
    for env_key in env_keys:
        value = str(os.environ.get(env_key) or "").strip()
        if value:
            return value
    return ""


def safe_channel_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return text


def format_timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def shift_time(time_str: str, seconds_offset: int = -2) -> str:
    try:
        start_str, end_str = time_str.split(" --> ")

        def adjust(value: str) -> str:
            parsed = datetime.strptime(value.strip(), "%H:%M:%S,%f")
            shifted = parsed + timedelta(seconds=seconds_offset)
            if shifted.year < 1900:
                return "00:00:00,000"
            return shifted.strftime("%H:%M:%S,%f")[:-3].replace(".", ",")

        return f"{adjust(start_str)} --> {adjust(end_str)}"
    except Exception:
        return time_str


def clean_ai_garbage(text: str) -> str:
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"\*.*", "", text)
    return text.strip()


def convert_to_million_vnd(text: str, currency_rate: int = 4000) -> str:
    pattern = r"(\d+(?:\.\d+)?)\s*(nghin|van|nghìn|vạn)?\s*(te|nhan dan te|tệ|nhân dân tệ|¥|元|CNY)"

    def replace_func(match: re.Match[str]) -> str:
        try:
            value = float(match.group(1))
            unit = str(match.group(2) or "").lower()
            if unit in {"van", "vạn"}:
                value *= 10000
            elif unit in {"nghin", "nghìn"}:
                value *= 1000
            total_vnd = int(value * currency_rate)
            millions = total_vnd / 1000000
            if millions >= 1:
                if millions == int(millions):
                    return f"{int(millions)} triệu đồng"
                if (millions * 10) % 10 == 5:
                    return f"{int(millions)} triệu rưỡi"
                return f"{millions:.1f} triệu đồng".replace(".", ",")
            return f"{total_vnd // 1000} nghìn đồng"
        except Exception:
            return match.group(0)

    return re.sub(pattern, replace_func, text, flags=re.IGNORECASE)


def parse_srt(file_path: Path) -> list[SubtitleItem]:
    content = file_path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    blocks = re.split(r"\n\n", content.strip())
    items: list[SubtitleItem] = []
    for block in blocks:
        lines = block.split("\n")
        if len(lines) >= 3:
            items.append(SubtitleItem(lines[0].strip(), lines[1].strip(), " ".join(lines[2:]).strip()))
    return items


def write_srt(path: Path, segments: list[SubtitleSegment]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for index, segment in enumerate(segments, start=1):
            handle.write(
                f"{index}\n"
                f"{format_timestamp(segment.start)} --> {format_timestamp(segment.end)}\n"
                f"{segment.text.strip()}\n\n"
            )


class ProcessingWorkflow:
    """New orchestrator for active-channel subtitle and translation processing."""

    def __init__(
        self,
        root: str | Path,
        settings: dict,
        active_channel: ActiveChannelState,
        transcriber: Transcriber | None = None,
        translator: SubtitleTranslator | None = None,
        tts_service: TTSService | None = None,
        render_service: RenderService | None = None,
        sheet_repository: Any = None,
        channel_cfg: dict | None = None,
        voices: dict | None = None,
        logger: Any = None,
    ):
        self.root = Path(root)
        self.settings = settings
        self.active_channel = active_channel
        self.transcriber = transcriber
        self.translator = translator
        self.tts_service = tts_service or TTSService(settings=settings, logger=logger)
        self.render_service = render_service or RenderService(logger=logger)
        self.sheet_repository = sheet_repository
        self.channel_cfg = channel_cfg or {}
        self.voices = voices or {}
        self.logger = logger
        self.source_dir = Path(str(settings.get("processing_source_dir") or LEGACY_SOURCE_DIR))
        self.processing_dir = Path(str(settings.get("processing_work_dir") or LEGACY_PROCESSING_DIR))
        self.batch_size = int(settings.get("subtitle_translation_batch_size", 10))

    def log(self, event: str, **fields: Any) -> None:
        if self.logger is not None and hasattr(self.logger, "worker"):
            metadata = dict(fields)
            metadata.pop("channel_id", None)
            metadata.pop("channel_name", None)
            metadata.pop("source_folder_id", None)
            self.logger.worker(
                event,
                channel_id=self.active_channel.channel_id,
                channel_name=self.active_channel.channel_name,
                source_folder_id=self.active_channel.source_folder_id,
                **metadata,
            )

    def _transcriber(self) -> Transcriber:
        if self.transcriber is None:
            self.transcriber = FasterWhisperTranscriber(str(self.settings.get("subtitle_whisper_model_size", "medium")))
        return self.transcriber

    def _translator(self) -> SubtitleTranslator:
        if self.translator is None:
            api_key = _first_config_value(
                self.settings,
                "subtitle_translation_api_key",
                (
                    "SUBTITLE_TRANSLATION_API_KEY",
                    "YT_SUBTITLE_TRANSLATION_API_KEY",
                    "DASHSCOPE_API_KEY",
                    "YT_DASHSCOPE_API_KEY",
                    "QWEN_API_KEY",
                    "YT_QWEN_API_KEY",
                    "OPENAI_API_KEY",
                    "YT_OPENAI_API_KEY",
                ),
            )
            base_url = _first_config_value(
                self.settings,
                "subtitle_translation_base_url",
                ("SUBTITLE_TRANSLATION_BASE_URL", "YT_SUBTITLE_TRANSLATION_BASE_URL"),
            ) or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
            model_name = _first_config_value(
                self.settings,
                "subtitle_translation_model",
                ("SUBTITLE_TRANSLATION_MODEL", "YT_SUBTITLE_TRANSLATION_MODEL"),
            ) or "qwen-plus"
            currency_rate = int(self.settings.get("subtitle_translation_currency_rate", 4000))
            self.translator = OpenAISubtitleTranslator(api_key, base_url, model_name, currency_rate=currency_rate)
        return self.translator

    def generate_subtitles(self) -> int:
        if self.source_dir.exists():
            if not self.source_dir.is_dir():
                raise ProcessingWorkflowError(f"processing source folder is not a directory: {self.source_dir}")
            self.log("processing_source_folder_exists", source_dir=str(self.source_dir))
        else:
            self.source_dir.mkdir(parents=True, exist_ok=True)
            self.log("processing_source_folder_created", source_dir=str(self.source_dir))
        self.processing_dir.mkdir(parents=True, exist_ok=True)
        videos = sorted(path for path in self.source_dir.iterdir() if path.is_file() and path.suffix.lower() == ".mp4")
        self.log("processing_subtitle_scan", source_dir=str(self.source_dir), videos=len(videos))
        if not videos:
            self.log("processing_subtitle_no_videos", source_dir=str(self.source_dir))
            return 0
        created = 0
        for video_path in videos:
            srt_path = self.source_dir / f"{video_path.stem}.srt"
            self.log("processing_subtitle_started", video_path=str(video_path), subtitle_path=str(srt_path))
            segments = self._transcriber().transcribe(video_path)
            write_srt(srt_path, segments)
            shutil.move(str(video_path), str(self.processing_dir / video_path.name))
            shutil.move(str(srt_path), str(self.processing_dir / srt_path.name))
            created += 1
            self.log("processing_subtitle_finished", video_path=str(self.processing_dir / video_path.name), subtitle_path=str(self.processing_dir / srt_path.name))
        return created

    def translate_subtitles(self) -> int:
        if not self.processing_dir.exists():
            raise ProcessingWorkflowError(f"processing work folder not found: {self.processing_dir}")
        srt_files = sorted(path for path in self.processing_dir.iterdir() if path.is_file() and path.suffix.lower() == ".srt" and not path.name.endswith("_vi.srt"))
        self.log("processing_translation_scan", processing_dir=str(self.processing_dir), subtitles=len(srt_files))
        translated_count = 0
        for srt_path in srt_files:
            output_path = self.processing_dir / f"{srt_path.stem}_vi.srt"
            items = parse_srt(srt_path)
            self.log("processing_translation_started", subtitle_path=str(srt_path), output_path=str(output_path), items=len(items))
            with output_path.open("w", encoding="utf-8") as handle:
                for index in range(0, len(items), self.batch_size):
                    batch = items[index : index + self.batch_size]
                    translated = self._translator().translate_batch(batch)
                    for item in batch:
                        text = translated.get(item.id, item.text)
                        handle.write(f"{item.id}\n{shift_time(item.time, seconds_offset=-2)}\n{text}\n\n")
                    time.sleep(float(self.settings.get("subtitle_translation_batch_delay_seconds", 0.5)))
            translated_count += 1
            self.log("processing_translation_finished", subtitle_path=str(srt_path), output_path=str(output_path))
        return translated_count

    def _resolve_path(self, value: Any) -> Path:
        path = Path(str(value))
        if path.is_absolute():
            return path
        return (self.root / path).resolve()

    def _voice_cfg(self) -> tuple[str, dict]:
        voice_id = str(self.channel_cfg.get("voice_id", "")).strip()
        if not voice_id:
            raise ProcessingWorkflowError(f"Missing voice_id for channel_id={self.active_channel.channel_id}")
        if voice_id not in self.voices:
            raise ProcessingWorkflowError(f"Voice not found in VOICE_CONFIG: {voice_id}")
        voice_cfg = dict(self.voices[voice_id])
        if not to_bool(voice_cfg.get("active"), True):
            raise ProcessingWorkflowError(f"Voice is inactive in VOICE_CONFIG: {voice_id}")

        raw_channel = self.channel_cfg.get("raw") or {}
        for key in ("ref_text", "language", "speed", "pitch"):
            value = raw_channel.get(key) or self.channel_cfg.get(key)
            if value not in (None, ""):
                voice_cfg[key] = value

        voice_name = str(
            raw_channel.get("voice_name")
            or self.channel_cfg.get("voice_name")
            or raw_channel.get("voice")
            or raw_channel.get("voice_file")
            or raw_channel.get("reference_voice")
            or ""
        ).strip()
        if voice_name:
            voices_dir = self._resolve_path(self.settings.get("voices_dir", "runtime/voices"))
            selected_voice_path = str(resolve_voice_path(voice_name, voices_dir, self.settings.get("default_voice_name", "")))
            voice_cfg["ref_audio_path"] = selected_voice_path
            voice_cfg["reference_audio"] = selected_voice_path
            voice_cfg["voice_path"] = selected_voice_path

        engine = str(
            voice_cfg.get("tts_engine")
            or voice_cfg.get("engine")
            or self.settings.get("voice_engine", "omnivoice_local")
        ).strip().lower()
        voice_cfg.setdefault("engine", engine)
        voice_cfg.setdefault("tts_engine", engine)
        voice_cfg.setdefault("omnivoice_model_name", self.settings.get("omnivoice_model_name", "k2-fsa/OmniVoice"))
        voice_cfg.setdefault("omnivoice_device", self.settings.get("omnivoice_device", "auto"))
        voice_cfg.setdefault("omnivoice_local_files_only", self.settings.get("omnivoice_local_files_only", True))
        if engine in {"omnivoice", "omnivoice_local", "local_omnivoice"}:
            missing = [name for name in ("ref_audio_path", "ref_text") if not str(voice_cfg.get(name, "")).strip()]
            if missing:
                raise ProcessingWorkflowError(f"Missing OmniVoice field(s) for channel_id={self.active_channel.channel_id}: {', '.join(missing)}")
        return voice_id, voice_cfg

    def _subtitle_text(self, srt_path: Path) -> str:
        items = parse_srt(srt_path)
        return " ".join(item.text for item in items if item.text).strip()

    def render_voice_cloned_videos(self) -> tuple[int, int]:
        if not self.channel_cfg:
            self.log("processing_voice_clone_skipped", reason="channel_config_not_loaded")
            return 0, 0
        output_folder_raw = str(self.channel_cfg.get("output_folder", "")).strip()
        if not output_folder_raw:
            safe_name = safe_channel_name(str(self.active_channel.channel_name))
            if safe_name:
                output_folder_raw = f"runtime/output/{self.active_channel.channel_id}_{safe_name}"
            else:
                output_folder_raw = f"runtime/output/{self.active_channel.channel_id}"
            self.channel_cfg["output_folder"] = output_folder_raw
            self.log(
                "processing_output_folder_generated",
                channel_id=self.active_channel.channel_id,
                output_folder=output_folder_raw,
            )
            if self.sheet_repository is not None and hasattr(self.sheet_repository, "update_channel_fields_by_channel_id"):
                self.sheet_repository.update_channel_fields_by_channel_id(
                    self.active_channel.channel_id,
                    {"output_folder": output_folder_raw},
                )
                self.log(
                    "processing_channel_config_updated",
                    channel_id=self.active_channel.channel_id,
                    output_folder=output_folder_raw,
                    updated=True,
                )
            else:
                self.log(
                    "processing_channel_config_updated",
                    channel_id=self.active_channel.channel_id,
                    output_folder=output_folder_raw,
                    updated=False,
                )
        else:
            self.log(
                "processing_output_folder_selected",
                channel_id=self.active_channel.channel_id,
                output_folder=output_folder_raw,
                generated=False,
            )
            self.log(
                "processing_channel_config_updated",
                channel_id=self.active_channel.channel_id,
                output_folder=output_folder_raw,
                updated=False,
            )
        output_dir = self._resolve_path(output_folder_raw)
        if output_dir.exists():
            if not output_dir.is_dir():
                raise ProcessingWorkflowError(f"output_folder is not a folder: {output_dir}")
            self.log("processing_output_folder_exists", output_folder=str(output_dir))
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            self.log("processing_output_folder_created", output_folder=str(output_dir))
        temp_dir = self.root / self.settings.get("temp_dir", "runtime/temp") / self.active_channel.channel_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        voice_id, voice_cfg = self._voice_cfg()
        subtitles = sorted(path for path in self.processing_dir.iterdir() if path.is_file() and path.name.endswith("_vi.srt"))
        self.log("processing_voice_clone_scan", processing_dir=str(self.processing_dir), subtitles=len(subtitles), voice_id=voice_id)
        voice_tracks = 0
        rendered = 0
        keep_audio = bool(self.settings.get("processing_keep_voice_audio", False))
        for subtitle_path in subtitles:
            base_stem = subtitle_path.stem[:-3] if subtitle_path.stem.endswith("_vi") else subtitle_path.stem
            video_path = next((self.processing_dir / f"{base_stem}{ext}" for ext in (".mp4", ".mkv", ".avi", ".mov") if (self.processing_dir / f"{base_stem}{ext}").exists()), None)
            if video_path is None:
                self.log("processing_render_skipped", subtitle_path=str(subtitle_path), reason="matching_video_not_found")
                continue
            text = self._subtitle_text(subtitle_path)
            if not text:
                self.log("processing_voice_clone_skipped", subtitle_path=str(subtitle_path), reason="empty_subtitle_text")
                continue
            voice_audio = temp_dir / f"{base_stem}_voice.wav"
            output_video = output_dir / f"{self.active_channel.channel_id}_{base_stem}.mp4"
            render_cfg = dict(self.channel_cfg)
            render_cfg["subtitle_path"] = str(subtitle_path)
            self.log("processing_voice_clone_started", subtitle_path=str(subtitle_path), voice_audio=str(voice_audio), voice_id=voice_id)
            self.tts_service.create_voice(text, voice_audio, voice_cfg, self.settings.get("google_key_dir", ""))
            voice_tracks += 1
            self.log("processing_render_started", video_path=str(video_path), output_path=str(output_video))
            self.render_service.render_video(video_path, voice_audio, output_video, render_cfg)
            rendered += 1
            self.log("processing_render_finished", video_path=str(video_path), output_path=str(output_video))
            if not keep_audio:
                try:
                    voice_audio.unlink()
                except FileNotFoundError:
                    pass
        return voice_tracks, rendered

    def run(self) -> ProcessingWorkflowResult:
        self.log("processing_workflow_started", source_dir=str(self.source_dir), processing_dir=str(self.processing_dir))
        created = self.generate_subtitles()
        translated = self.translate_subtitles()
        voice_tracks, rendered = self.render_voice_cloned_videos()
        self.log("processing_workflow_finished", subtitles_created=created, subtitles_translated=translated, voice_tracks_created=voice_tracks, videos_rendered=rendered)
        return ProcessingWorkflowResult(
            active_channel_id=self.active_channel.channel_id,
            active_channel_name=self.active_channel.channel_name,
            source_dir=str(self.source_dir),
            processing_dir=str(self.processing_dir),
            subtitles_created=created,
            subtitles_translated=translated,
            voice_tracks_created=voice_tracks,
            videos_rendered=rendered,
        )
