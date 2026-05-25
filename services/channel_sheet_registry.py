from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from processors.sheet_client import to_bool, to_int
from services.voice_registry import resolve_voice_path


@dataclass(frozen=True)
class ChannelSheetConfig:
    channel_id: str
    channel_name: str
    input_folder: str
    output_folder: str
    voice_id: str
    voice_name: str
    voice_path: str
    music_pack_id: str = ""
    overlay_pack_id: str = ""
    render_preset_id: str = ""
    youtube_oauth_token_json: str = ""
    privacy_status: str = "private"
    enabled: bool = True
    daily_limit: int = 0
    worker_id: str = ""
    last_error: str = ""
    ref_text: str = ""
    source_folder_id: str = ""
    raw: dict | None = None


class ChannelSheetRegistry:
    """Google Sheet backed channel registry for production channel control."""

    def __init__(
        self,
        sheet_repository: Any,
        settings: dict,
        root: str | Path,
        worksheet_name: str | None = None,
    ):
        self.sheet_repository = sheet_repository
        self.settings = settings
        self.root = Path(root)
        self.worksheet_name = worksheet_name or settings.get("channel_config_sheet_name", "CHANNEL_CONFIG")

    def resolve_path(self, value: Any) -> str:
        if hasattr(self.sheet_repository, "resolve_path"):
            return self.sheet_repository.resolve_path(value)
        path = Path(str(value or ""))
        if path.is_absolute():
            return str(path)
        return str((self.root / path).resolve())

    def _load_rows(self) -> list[dict]:
        loader = getattr(self.sheet_repository, "load_channel_registry_rows", None)
        if callable(loader):
            return loader(self.worksheet_name)
        sheet = getattr(self.sheet_repository, "sheet", None)
        if sheet is None:
            raise ValueError("sheet_repository must expose sheet or load_channel_registry_rows")
        rows = sheet.map_by(self.worksheet_name, "channel_id")
        return list(rows.values())

    def _voice_path_for(self, row: dict) -> str:
        voice_name = str(
            row.get("voice_name")
            or row.get("voice")
            or row.get("voice_file")
            or row.get("reference_voice")
            or ""
        ).strip()
        default_voice_name = str(self.settings.get("default_voice_name", "")).strip()
        if not voice_name and not default_voice_name:
            return ""
        voices_dir = Path(self.resolve_path(self.settings.get("voices_dir", "runtime/voices")))
        return str(resolve_voice_path(voice_name, voices_dir, default_voice_name))

    def normalize_row(self, row: dict) -> ChannelSheetConfig:
        channel_id = str(row.get("channel_id", "")).strip()
        if not channel_id:
            raise ValueError("channel_id is required")
        input_folder = str(row.get("input_folder", "")).strip()
        if not input_folder:
            raise ValueError(f"input_folder is required for channel_id={channel_id}")
        privacy_status = str(row.get("privacyStatus") or row.get("privacy_status") or "private").strip() or "private"
        token_path_raw = str(
            row.get("youtube_token")
            or row.get("youtube_oauth_token_json")
            or row.get("youtube_token_path")
            or row.get("youtube_oauth_token_path")
            or ""
        ).strip()
        output_folder = str(row.get("output_folder", "")).strip()
        return ChannelSheetConfig(
            channel_id=channel_id,
            channel_name=str(row.get("channel_name", "")).strip(),
            input_folder=self.resolve_path(input_folder),
            output_folder=self.resolve_path(output_folder) if output_folder else "",
            voice_id=str(row.get("voice_id", "")).strip(),
            voice_name=str(row.get("voice_name", "")).strip(),
            voice_path=self._voice_path_for(row),
            music_pack_id=str(row.get("music_pack_id", "")).strip(),
            overlay_pack_id=str(row.get("overlay_pack_id", "")).strip(),
            render_preset_id=str(row.get("render_preset_id", "")).strip(),
            youtube_oauth_token_json=self.resolve_path(token_path_raw) if token_path_raw else "",
            privacy_status=privacy_status,
            enabled=to_bool(row.get("enabled"), True),
            daily_limit=to_int(row.get("daily_limit"), 0),
            worker_id=str(row.get("worker_id", "")).strip(),
            last_error=str(row.get("last_error", "")).strip(),
            ref_text=str(row.get("ref_text", "")).strip(),
            source_folder_id=str(row.get("source_folder_id", "")).strip(),
            raw=row,
        )

    def enabled_channels(self, max_channels: int | None = None) -> list[ChannelSheetConfig]:
        channels: list[ChannelSheetConfig] = []
        for row in self._load_rows():
            channel = self.normalize_row(row)
            if not channel.enabled:
                continue
            channels.append(channel)
            if max_channels is not None and len(channels) >= max_channels:
                break
        return channels

    def selected_channel(self, channel_id: str) -> ChannelSheetConfig:
        requested = str(channel_id or "").strip()
        if not requested:
            raise ValueError("channel_id is required")
        for row in self._load_rows():
            if str(row.get("channel_id", "")).strip() != requested:
                continue
            channel = self.normalize_row(row)
            if not channel.enabled:
                raise ValueError(f"channel is disabled: {requested}")
            return channel
        raise KeyError(f"channel_id not found: {requested}")
