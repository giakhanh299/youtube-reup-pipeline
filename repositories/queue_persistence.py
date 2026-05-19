from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import os
import tempfile
from typing import Protocol


@dataclass(frozen=True)
class QueueJobState:
    job_id: str
    status: str
    channel_id: str = ""
    video_path: str = ""
    output_path: str = ""
    error: str = ""
    retry_count: int = 0


class QueuePersistence(Protocol):
    """Persistence contract for resumable queue jobs."""

    def save_job_state(self, state: QueueJobState) -> None:
        raise NotImplementedError

    def load_job_state(self, job_id: str) -> QueueJobState | None:
        raise NotImplementedError

    def mark_failed(self, job_id: str, error: str) -> None:
        raise NotImplementedError


class NullQueuePersistence:
    """No-op implementation used until persistent queue storage is added."""

    def save_job_state(self, state: QueueJobState) -> None:
        return None

    def load_job_state(self, job_id: str) -> QueueJobState | None:
        return None

    def mark_failed(self, job_id: str, error: str) -> None:
        return None


class JsonQueuePersistence:
    """Crash-safe JSON file queue state store."""

    def __init__(self, state_dir: str | Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, job_id: str) -> Path:
        safe_job_id = "".join(c if c.isalnum() or c in "._-" else "_" for c in job_id).strip("_")
        if not safe_job_id:
            raise ValueError("job_id is required")
        return self.state_dir / f"{safe_job_id}.json"

    def save_job_state(self, state: QueueJobState) -> None:
        path = self._path_for(state.job_id)
        payload = json.dumps(asdict(state), ensure_ascii=False, indent=2)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=self.state_dir, suffix=".tmp") as handle:
            handle.write(payload)
            temp_name = handle.name
        os.replace(temp_name, path)

    def load_job_state(self, job_id: str) -> QueueJobState | None:
        path = self._path_for(job_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return QueueJobState(**data)

    def mark_failed(self, job_id: str, error: str) -> None:
        existing = self.load_job_state(job_id)
        if existing:
            retry_count = existing.retry_count + 1
            state = QueueJobState(
                job_id=existing.job_id,
                status="ERROR",
                channel_id=existing.channel_id,
                video_path=existing.video_path,
                output_path=existing.output_path,
                error=error,
                retry_count=retry_count,
            )
        else:
            state = QueueJobState(job_id=job_id, status="ERROR", error=error, retry_count=1)
        self.save_job_state(state)

    def failed_jobs(self) -> list[QueueJobState]:
        jobs: list[QueueJobState] = []
        for path in sorted(self.state_dir.glob("*.json")):
            state = QueueJobState(**json.loads(path.read_text(encoding="utf-8")))
            if state.status == "ERROR":
                jobs.append(state)
        return jobs
