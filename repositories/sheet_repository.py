from __future__ import annotations

from pathlib import Path
from typing import Any

from logs.structured_logger import NullLogger
from processors.sheet_client import SheetConfig, to_bool, to_float, to_int
from utils.retry import RetryStrategy, retry_google_api


class SheetRepository:
    """Repository wrapper around Google Sheet config and queue rows."""

    def __init__(
        self,
        sheet: SheetConfig,
        root: Path,
        retry_strategy: RetryStrategy | None = None,
        logger: Any = None,
    ):
        self.sheet = sheet
        self.root = root
        self.retry_strategy = retry_strategy
        self.logger = logger or NullLogger()

    @classmethod
    def from_settings(
        cls,
        settings: dict,
        root: Path,
        retry_strategy: RetryStrategy | None = None,
        logger: Any = None,
    ) -> "SheetRepository":
        sheet = SheetConfig(settings["spreadsheet_id"], settings["service_account_json"])
        retry_google_api(sheet.connect, retry_strategy, "sheets_connect")
        return cls(sheet, root, retry_strategy=retry_strategy, logger=logger)

    def resolve_path(self, value: Any) -> str:
        if not value:
            return ""
        path = Path(str(value))
        if path.is_absolute():
            return str(path)
        return str((self.root / path).resolve())

    def normalize_channel(self, row: dict) -> dict:
        return {
            "enabled": to_bool(row.get("enabled"), True),
            "input_folder": row.get("input_folder", ""),
            "output_folder": row.get("output_folder", ""),
            "voice_id": row.get("voice_id", ""),
            "music_pack_id": row.get("music_pack_id", ""),
            "overlay_pack_id": row.get("overlay_pack_id", ""),
            "render_preset_id": row.get("render_preset_id", ""),
            "subtitle_style_id": row.get("subtitle_style_id", ""),
            "use_nvenc": to_bool(row.get("use_nvenc"), True),
            "background_blur": to_bool(row.get("background_blur"), True),
            "blur_strength": to_int(row.get("blur_strength"), 28),
            "speed": to_float(row.get("speed"), 1.0),
            "logo_path": self.resolve_path(row.get("logo_path", "")),
            "logo_opacity": to_float(row.get("logo_opacity"), 0.16),
            "logo_x": row.get("logo_x", 30),
            "logo_y": row.get("logo_y", 40),
            "music_path": self.resolve_path(row.get("music_path", "")),
            "music_volume": to_float(row.get("music_volume"), 0.07),
            "channel_description": row.get("channel_description", ""),
            "channel_style_prompt": row.get("channel_style_prompt", ""),
            "title_template": row.get("title_template", ""),
            "description_template": row.get("description_template", ""),
            "tags_default": row.get("tags_default", ""),
            "metadata_ai_enabled": to_bool(row.get("metadata_ai_enabled"), False),
            "raw": row,
        }

    def normalize_voice(self, row: dict) -> dict:
        return {
            "engine": row.get("engine", row.get("tts_engine", "google")),
            "tts_engine": row.get("tts_engine", row.get("engine", "google")),
            "language": row.get("language", row.get("language_code", "vi-VN")),
            "language_code": row.get("language_code", row.get("language", "vi-VN")),
            "name": row.get("name", "vi-VN-Wavenet-A"),
            "gender": row.get("gender", "FEMALE"),
            "speaking_rate": to_float(row.get("speaking_rate", row.get("speed")), 1.0),
            "speed": to_float(row.get("speed", row.get("speaking_rate")), 1.0),
            "pitch": to_float(row.get("pitch"), 0.0),
            "volume_gain_db": to_float(row.get("volume_gain_db"), 0.0),
            "command": row.get("command", ""),
            "ref_audio_path": self.resolve_path(row.get("ref_audio_path", "")),
            "ref_text": row.get("ref_text", ""),
            "active": to_bool(row.get("active"), True),
            "raw": row,
        }

    def normalize_upload_channel_config(self, row: dict) -> dict:
        return {
            "channel_key": str(row.get("channel_key", "")).strip(),
            "channel_name": str(row.get("channel_name", "")).strip(),
            "account_name": str(row.get("account_name", "")).strip(),
            "youtube_token_path": self.resolve_path(row.get("youtube_token_path", "")),
            "voice_name": str(row.get("voice_name", "")).strip(),
            "voice_speed": to_float(row.get("voice_speed"), 1.0),
            "voice_pitch": to_float(row.get("voice_pitch"), 0.0),
            "language": str(row.get("language", "")).strip(),
            "default_categoryId": str(row.get("default_categoryId", "")).strip(),
            "default_privacyStatus": str(row.get("default_privacyStatus", "")).strip(),
            "title_template": str(row.get("title_template", "")).strip(),
            "description_template": str(row.get("description_template", "")).strip(),
            "tags_default": str(row.get("tags_default", "")).strip(),
            "enabled": to_bool(row.get("enabled"), True),
            "notes": str(row.get("notes", "")).strip(),
            "raw": row,
        }

    def merge_pack_into_channel(
        self,
        channel: dict,
        music_packs: dict,
        overlay_packs: dict,
        render_presets: dict,
    ) -> dict:
        cfg = dict(channel)

        preset = render_presets.get(channel.get("render_preset_id", ""), {})
        if preset:
            cfg["background_blur"] = to_bool(preset.get("background_blur"), cfg.get("background_blur", True))
            cfg["blur_strength"] = to_int(preset.get("blur_strength"), cfg.get("blur_strength", 28))
            cfg["speed"] = to_float(preset.get("speed"), cfg.get("speed", 1.0))
            cfg["use_nvenc"] = to_bool(preset.get("use_nvenc"), cfg.get("use_nvenc", True))

        music = music_packs.get(channel.get("music_pack_id", ""), {})
        if music:
            cfg["music_path"] = self.resolve_path(music.get("music_path", cfg.get("music_path", "")))
            cfg["music_volume"] = to_float(music.get("music_volume"), cfg.get("music_volume", 0.07))

        overlay = overlay_packs.get(channel.get("overlay_pack_id", ""), {})
        if overlay:
            cfg["logo_path"] = self.resolve_path(overlay.get("logo_path", cfg.get("logo_path", "")))
            cfg["logo_opacity"] = to_float(overlay.get("logo_opacity"), cfg.get("logo_opacity", 0.16))
            cfg["logo_x"] = overlay.get("logo_x", cfg.get("logo_x", 30))
            cfg["logo_y"] = overlay.get("logo_y", cfg.get("logo_y", 40))
            cfg["background_blur"] = to_bool(overlay.get("background_blur"), cfg.get("background_blur", True))
            cfg["blur_strength"] = to_int(overlay.get("blur_strength"), cfg.get("blur_strength", 28))
        return cfg

    def load_all(self) -> tuple[SheetConfig, dict, dict, dict, dict, dict, list[dict]]:
        channels_raw = retry_google_api(
            lambda: self.sheet.map_by("CHANNEL_CONFIG", "channel_id"),
            self.retry_strategy,
            "sheets_read_channel_config",
        )
        voices_raw = retry_google_api(
            lambda: self.sheet.map_by("VOICE_CONFIG", "voice_id"),
            self.retry_strategy,
            "sheets_read_voice_config",
        )
        channels = {key: self.normalize_channel(value) for key, value in channels_raw.items()}
        voices = {key: self.normalize_voice(value) for key, value in voices_raw.items()}
        music_packs = retry_google_api(
            lambda: self.sheet.map_by("MUSIC_PACK", "music_pack_id"),
            self.retry_strategy,
            "sheets_read_music_pack",
        )
        overlay_packs = retry_google_api(
            lambda: self.sheet.map_by("OVERLAY_PACK", "overlay_pack_id"),
            self.retry_strategy,
            "sheets_read_overlay_pack",
        )
        render_presets = retry_google_api(
            lambda: self.sheet.map_by("RENDER_PRESET", "render_preset_id"),
            self.retry_strategy,
            "sheets_read_render_preset",
        )
        queue = retry_google_api(
            lambda: self.sheet.rows("VIDEO_QUEUE"),
            self.retry_strategy,
            "sheets_read_video_queue",
        )
        return self.sheet, channels, voices, music_packs, overlay_packs, render_presets, queue

    def update_status_by_job_id(
        self,
        job_id: str,
        status: str,
        output_path: str = "",
        error: str = "",
        youtube_video_id: str = "",
        upload_time: str = "",
    ) -> None:
        retry_google_api(
            lambda: self.sheet.update_status_by_job_id(
                job_id,
                status,
                output_path=output_path,
                error=error,
                youtube_video_id=youtube_video_id,
                upload_time=upload_time,
            ),
            self.retry_strategy,
            "sheets_update_job_status",
        )

    def load_upload_jobs(self, worksheet_name: str) -> list[tuple[int, dict]]:
        return retry_google_api(
            lambda: self.sheet.rows_with_numbers(worksheet_name),
            self.retry_strategy,
            "sheets_read_upload_jobs",
        )

    def update_upload_result(
        self,
        worksheet_name: str,
        row_number: int,
        upload_status: str,
        youtube_video_id: str = "",
        upload_error: str = "",
        upload_time: str = "",
        retry_count: int | str | None = None,
        last_error: str = "",
        upload_started_at: str = "",
        upload_finished_at: str = "",
    ) -> None:
        retry_google_api(
            lambda: self.sheet.update_upload_result(
                worksheet_name,
                row_number,
                upload_status,
                youtube_video_id=youtube_video_id,
                upload_error=upload_error,
                upload_time=upload_time,
                retry_count=retry_count,
                last_error=last_error,
                upload_started_at=upload_started_at,
                upload_finished_at=upload_finished_at,
            ),
            self.retry_strategy,
            "sheets_update_upload_result",
        )

    def load_render_jobs(self, worksheet_name: str) -> list[tuple[int, dict]]:
        return retry_google_api(
            lambda: self.sheet.rows_with_numbers(worksheet_name),
            self.retry_strategy,
            "sheets_read_render_jobs",
        )

    def load_upload_channel_configs(self, worksheet_name: str = "Channel Config") -> dict[str, dict]:
        rows = retry_google_api(
            lambda: self.sheet.map_by(worksheet_name, "channel_key"),
            self.retry_strategy,
            "sheets_read_channel_config_upload",
        )
        configs = {}
        for key, row in rows.items():
            cfg = self.normalize_upload_channel_config(row)
            if cfg["enabled"]:
                configs[key] = cfg
        return configs

    def update_render_result(
        self,
        worksheet_name: str,
        row_number: int,
        render_status: str,
        audio_path: str = "",
        rendered_video_path: str = "",
        render_error: str = "",
    ) -> None:
        retry_google_api(
            lambda: self.sheet.update_render_result(
                worksheet_name,
                row_number,
                render_status,
                audio_path=audio_path,
                rendered_video_path=rendered_video_path,
                render_error=render_error,
            ),
            self.retry_strategy,
            "sheets_update_render_result",
        )

    def update_video_queue_fields_by_job_id(self, job_id: str, fields: dict[str, Any]) -> None:
        retry_google_api(
            lambda: self.sheet.update_video_queue_fields_by_job_id(job_id, fields),
            self.retry_strategy,
            "sheets_update_video_queue_metadata",
        )

    def upsert_uploaded_video(self, ledger_row: dict[str, Any]) -> str:
        return retry_google_api(
            lambda: self.sheet.upsert_uploaded_video(ledger_row),
            self.retry_strategy,
            "sheets_upsert_uploaded_video",
        )
