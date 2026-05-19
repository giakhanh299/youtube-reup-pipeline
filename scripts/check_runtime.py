from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.config_loader import ConfigLoader
from logs.structured_logger import StructuredLogger
from repositories.queue_persistence import JsonQueuePersistence, QueueJobState


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def check_ffmpeg() -> str:
    ffmpeg_path = shutil.which("ffmpeg")
    check(bool(ffmpeg_path), "ffmpeg is not available on PATH")
    result = subprocess.run(
        ["ffmpeg", "-version"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()[0]


def main() -> int:
    print("Runtime validation starting")

    settings = ConfigLoader(ROOT).load_settings()
    print("OK config loaded")

    log_dir = ROOT / settings.get("log_dir", "runtime/logs")
    state_dir = ROOT / settings.get("queue_state_dir", "runtime/state/queue")
    temp_dir = ROOT / settings.get("temp_dir", "runtime/temp")

    for directory in (log_dir, state_dir, temp_dir):
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".runtime_check"
        probe.write_text("ok", encoding="utf-8")
        check(probe.read_text(encoding="utf-8") == "ok", f"directory is not writable: {directory}")
        probe.unlink()
        print(f"OK writable: {directory}")

    logger = StructuredLogger(log_dir)
    logger.app("runtime_check")
    check((log_dir / "app.log").exists(), "app log was not written")
    print("OK logs volume")

    queue = JsonQueuePersistence(state_dir)
    queue.save_job_state(QueueJobState(job_id="runtime_check", status="READY_UPLOAD"))
    state = queue.load_job_state("runtime_check")
    check(state is not None and state.status == "READY_UPLOAD", "queue state was not persisted")
    print("OK queue persistence volume")

    ffmpeg_version = check_ffmpeg()
    print(f"OK {ffmpeg_version}")
    print("Runtime validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
