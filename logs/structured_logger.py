from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any


class StructuredLogger:
    """Small JSONL logger for app, error, retry, render, and upload logs."""

    def __init__(self, log_dir: str | Path):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _write(self, name: str, level: str, event: str, **fields: Any) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            **fields,
        }
        path = self.log_dir / f"{name}.log"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def app(self, event: str, **fields: Any) -> None:
        self._write("app", "INFO", event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self._write("error", "ERROR", event, **fields)

    def retry(self, event: str, **fields: Any) -> None:
        self._write("retry", "WARNING", event, **fields)

    def render(self, event: str, **fields: Any) -> None:
        self._write("render", "INFO", event, **fields)

    def upload(self, event: str, **fields: Any) -> None:
        self._write("upload", "INFO", event, **fields)

    def worker(self, event: str, **fields: Any) -> None:
        self._write("worker", "INFO", event, **fields)

    def scheduler(self, event: str, **fields: Any) -> None:
        self._write("scheduler", "INFO", event, **fields)

    def selenium(self, event: str, **fields: Any) -> None:
        self._write("selenium", "INFO", event, **fields)

    def docker(self, event: str, **fields: Any) -> None:
        self._write("docker", "INFO", event, **fields)

    def queue_recovery(self, event: str, **fields: Any) -> None:
        self._write("queue_recovery", "INFO", event, **fields)

    def telegram(self, event: str, **fields: Any) -> None:
        self._write("telegram", "INFO", event, **fields)


class NullLogger:
    """Logger interface that discards records."""

    def app(self, event: str, **fields: Any) -> None:
        return None

    def error(self, event: str, **fields: Any) -> None:
        return None

    def retry(self, event: str, **fields: Any) -> None:
        return None

    def render(self, event: str, **fields: Any) -> None:
        return None

    def upload(self, event: str, **fields: Any) -> None:
        return None

    def worker(self, event: str, **fields: Any) -> None:
        return None

    def scheduler(self, event: str, **fields: Any) -> None:
        return None

    def selenium(self, event: str, **fields: Any) -> None:
        return None

    def docker(self, event: str, **fields: Any) -> None:
        return None

    def queue_recovery(self, event: str, **fields: Any) -> None:
        return None

    def telegram(self, event: str, **fields: Any) -> None:
        return None
