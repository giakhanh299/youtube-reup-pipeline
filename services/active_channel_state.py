from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

from services.channel_sheet_registry import ChannelSheetConfig
from services.shared_channel_workspace import SharedChannelWorkspaceManager


@dataclass(frozen=True)
class ActiveChannelState:
    channel_id: str
    channel_name: str
    youtube_token_path: str
    source_folder_id: str = ""
    selected_at: str = ""


class ActiveChannelStateStore:
    """Stores the Telegram-selected channel without changing processing logic."""

    def __init__(self, root: str | Path, settings: dict | None = None, logger: Any = None):
        self.root = Path(root)
        self.settings = settings or {}
        self.logger = logger
        state_path = self.settings.get("active_channel_state_path", "runtime/state/active_channel.json")
        self.state_path = self._resolve(state_path)
        self.workspace = SharedChannelWorkspaceManager(self.root, self.settings, logger=logger)

    def _resolve(self, value: Any) -> Path:
        path = Path(str(value))
        if path.is_absolute():
            return path
        return (self.root / path).resolve()

    def log(self, event: str, **fields: Any) -> None:
        if self.logger is not None and hasattr(self.logger, "worker"):
            self.logger.worker(event, **fields)

    def select(self, channel: ChannelSheetConfig, resume: bool = False, clean_before_start: bool = False) -> ActiveChannelState:
        self.workspace.acquire(channel.channel_id, channel.channel_name)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if clean_before_start and not resume:
            self.workspace.clean(label="pre_start")
        state = ActiveChannelState(
            channel_id=channel.channel_id,
            channel_name=channel.channel_name,
            youtube_token_path=channel.youtube_oauth_token_json,
            source_folder_id=channel.source_folder_id,
            selected_at=datetime.now(timezone.utc).isoformat(),
        )
        self.state_path.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")
        self.log(
            "active_channel_selected",
            channel_id=state.channel_id,
            channel_name=state.channel_name,
            youtube_token_path=state.youtube_token_path,
            source_folder_id=state.source_folder_id,
            resume=resume,
            clean_before_start=clean_before_start,
        )
        return state

    def load(self) -> ActiveChannelState | None:
        if not self.state_path.exists():
            return None
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        return ActiveChannelState(
            channel_id=str(data.get("channel_id", "")).strip(),
            channel_name=str(data.get("channel_name", "")).strip(),
            youtube_token_path=str(data.get("youtube_token_path", "")).strip(),
            source_folder_id=str(data.get("source_folder_id", "")).strip(),
            selected_at=str(data.get("selected_at", "")).strip(),
        )

    def finish(self, clean_after_finish: bool = False) -> None:
        if clean_after_finish:
            self.workspace.clean(label="post_finish")
        try:
            self.state_path.unlink()
        except FileNotFoundError:
            pass
        self.workspace.release()
        self.log("active_channel_finished", state_path=str(self.state_path))
