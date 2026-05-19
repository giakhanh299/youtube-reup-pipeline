from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any


STATUS_GROUPS = {
    "pending": {"pending", "new"},
    "rendering": {"rendering", "processing"},
    "uploading": {"uploading"},
    "failed": {"failed", "error"},
    "completed": {"uploaded", "ready", "ready_upload", "done"},
}


@dataclass(frozen=True)
class DashboardControlEvent:
    action: str
    job_id: str = ""
    ts: str = ""


class DashboardStateBuilder:
    """Reads runtime files and logs for dashboard status."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _read_json_file(self, path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def queue_jobs(self) -> list[dict]:
        jobs = []
        state_dir = self.root / "runtime" / "state" / "queue"
        if not state_dir.exists():
            return jobs
        for path in sorted(state_dir.glob("*.json")):
            data = self._read_json_file(path)
            if data:
                jobs.append(data)
        return jobs

    def queue_counts(self, jobs: list[dict]) -> dict[str, int]:
        counts = {key: 0 for key in STATUS_GROUPS}
        for job in jobs:
            status = str(job.get("upload_state") or job.get("status", "")).strip().lower()
            for group, statuses in STATUS_GROUPS.items():
                if status in statuses:
                    counts[group] += 1
                    break
        return counts

    def account_usage(self, jobs: list[dict]) -> dict[str, int]:
        usage: dict[str, int] = {}
        for job in jobs:
            account = str(job.get("account_name") or job.get("channel_key") or "default")
            usage[account] = usage.get(account, 0) + 1
        return usage

    def retry_counts(self, jobs: list[dict]) -> dict[str, int]:
        return {
            str(job.get("job_id", "")): int(job.get("retry_count") or 0)
            for job in jobs
            if str(job.get("job_id", "")).strip()
        }

    def log_tail(self, name: str, limit: int = 50) -> list[dict]:
        path = self.root / "runtime" / "logs" / f"{name}.log"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
        events = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except Exception:
                events.append({"message": line})
        return events

    def throughput(self) -> dict[str, int]:
        upload_events = self.log_tail("upload", 200)
        render_events = self.log_tail("render", 200)
        return {
            "upload_events": len(upload_events),
            "render_events": len(render_events),
            "worker_events": len(self.log_tail("worker", 200)),
            "retry_events": len(self.log_tail("retry", 200)),
        }

    def snapshot(self) -> dict:
        jobs = self.queue_jobs()
        return {
            "queue_counts": self.queue_counts(jobs),
            "jobs": jobs,
            "account_usage": self.account_usage(jobs),
            "retry_counts": self.retry_counts(jobs),
            "throughput": self.throughput(),
            "logs": {
                "upload": self.log_tail("upload"),
                "render": self.log_tail("render"),
                "worker": self.log_tail("worker"),
                "retry": self.log_tail("retry"),
            },
        }


class DashboardControlStore:
    """Writes dashboard control intents without executing business logic."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.state_dir = self.root / "runtime" / "state" / "dashboard"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def record(self, action: str, job_id: str = "") -> DashboardControlEvent:
        allowed = {"retry", "skip", "pause", "resume"}
        if action not in allowed:
            raise ValueError(f"unsupported dashboard action: {action}")
        event = DashboardControlEvent(action, job_id, datetime.now(timezone.utc).isoformat())
        path = self.state_dir / "controls.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.__dict__, ensure_ascii=False) + "\n")
        if action in {"pause", "resume"}:
            (self.state_dir / "queue_control.json").write_text(
                json.dumps({"paused": action == "pause", "ts": event.ts}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return event
