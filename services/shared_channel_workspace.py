from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import shutil
import stat
from typing import Any


class ChannelJobAlreadyRunning(RuntimeError):
    pass


@dataclass(frozen=True)
class SharedChannelWorkspace:
    input_dir: Path
    processing_dir: Path
    output_dir: Path
    lock_path: Path


class SharedChannelWorkspaceManager:
    """Single-channel shared workspace with lock-file protection."""

    def __init__(self, root: str | Path, settings: dict | None = None, logger: Any = None):
        self.root = Path(root)
        settings = settings or {}
        self.logger = logger
        self.workspace = SharedChannelWorkspace(
            input_dir=self._resolve(settings.get("shared_input_dir", "runtime/input")),
            processing_dir=self._resolve(settings.get("shared_processing_dir", "runtime/processing")),
            output_dir=self._resolve(settings.get("shared_output_dir", "runtime/output")),
            lock_path=self._resolve(settings.get("active_channel_lock_path", "runtime/state/active_channel.lock")),
        )

    def _resolve(self, value: Any) -> Path:
        path = Path(str(value))
        if path.is_absolute():
            return path
        return (self.root / path).resolve()

    def ensure_dirs(self) -> None:
        self.workspace.input_dir.mkdir(parents=True, exist_ok=True)
        self.workspace.processing_dir.mkdir(parents=True, exist_ok=True)
        self.workspace.output_dir.mkdir(parents=True, exist_ok=True)
        self.workspace.lock_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **fields: Any) -> None:
        if self.logger is not None and hasattr(self.logger, "worker"):
            self.logger.worker(event, **fields)

    def acquire(self, channel_id: str, channel_name: str) -> None:
        self.ensure_dirs()
        payload = {
            "channel_id": channel_id,
            "channel_name": channel_name,
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            fd = os.open(str(self.workspace.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ChannelJobAlreadyRunning(f"active channel job lock exists: {self.workspace.lock_path}") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        self.log("shared_channel_lock_acquired", **payload, lock_path=str(self.workspace.lock_path))

    def release(self) -> None:
        try:
            self.workspace.lock_path.unlink()
            self.log("shared_channel_lock_released", lock_path=str(self.workspace.lock_path))
        except FileNotFoundError:
            return

    def clean(self, label: str = "cleanup") -> None:
        self.ensure_dirs()
        for folder in (self.workspace.input_dir, self.workspace.processing_dir, self.workspace.output_dir):
            self.clean_folder(folder, label=label)

    def clean_folder(self, folder: Path, label: str = "cleanup") -> None:
        folder.mkdir(parents=True, exist_ok=True)
        removed = 0
        for child in folder.iterdir():
            self._remove_path(child)
            removed += 1
        self.log("shared_channel_workspace_cleaned", folder=str(folder), removed=removed, label=label)

    def clean_processing_and_output(self, label: str = "cleanup") -> None:
        self.ensure_dirs()
        for folder in (self.workspace.processing_dir, self.workspace.output_dir):
            self.clean_folder(folder, label=label)

    def _remove_path(self, path: Path) -> None:
        try:
            if path.is_dir():
                shutil.rmtree(path, onerror=self._remove_readonly)
            else:
                path.unlink()
        except PermissionError:
            os.chmod(path, stat.S_IWRITE)
            path.unlink()

    def _remove_readonly(self, _func: Any, path: str, _exc_info: Any) -> None:
        os.chmod(path, stat.S_IWRITE)
        Path(path).unlink()
