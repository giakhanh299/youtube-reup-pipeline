from __future__ import annotations

from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.config_loader import ConfigLoader
from integrations.youtube.youtube_api_uploader import YouTubeApiUploader
from logs.structured_logger import StructuredLogger
from repositories.queue_persistence import QueueJobState
from utils.retry import RetryStrategy


TEST_VIDEO = ROOT / "runtime" / "test" / "test.mp4"


def main() -> int:
    """Manual private upload smoke test.

    How to run from the repo root:
      python scripts/test_youtube_upload.py

    Required config can be placed in .env:
      YT_YOUTUBE_OAUTH_CREDENTIALS_JSON=E:/path/to/oauth_client.json
      YT_YOUTUBE_OAUTH_TOKEN_JSON=runtime/state/youtube/token.json

    This script performs a real private YouTube upload of runtime/test/test.mp4.
    It does not read or update VIDEO_QUEUE.
    """

    try:
        if not TEST_VIDEO.exists():
            raise FileNotFoundError(f"Test video not found: {TEST_VIDEO}")

        settings = ConfigLoader(ROOT).load_settings()
        credentials_path = str(settings.get("youtube_oauth_credentials_json", "")).strip()
        token_path = str(settings.get("youtube_oauth_token_json", "")).strip()
        if not credentials_path:
            raise ValueError("Missing YT_YOUTUBE_OAUTH_CREDENTIALS_JSON or youtube_oauth_credentials_json")
        if not token_path:
            raise ValueError("Missing YT_YOUTUBE_OAUTH_TOKEN_JSON or youtube_oauth_token_json")

        logger = StructuredLogger(ROOT / settings.get("log_dir", "runtime/logs"))
        retry_strategy = RetryStrategy(
            max_attempts=int(settings.get("retry_max_attempts", 3)),
            base_delay=float(settings.get("retry_base_delay", 1.0)),
            max_delay=float(settings.get("retry_max_delay", 30.0)),
            logger=logger,
        )

        def print_state(state: str, _job: QueueJobState) -> None:
            print(f"Upload state: {state}")

        def print_progress(progress: float) -> None:
            print(f"Upload progress: {progress * 100:.1f}%")

        uploader = YouTubeApiUploader.from_settings(
            settings,
            retry_strategy=retry_strategy,
            logger=logger,
            state_callback=print_state,
        )
        uploader.progress_callback = print_progress

        job = QueueJobState(
            job_id="manual_test_upload",
            status="READY_UPLOAD",
            output_path=str(TEST_VIDEO),
            title="Private upload API test",
            description="Minimal private upload test from reup pipeline.",
            tags=["test", "api"],
            category_id="22",
            privacy_status="private",
        )

        print(f"Uploading private test video: {TEST_VIDEO}")
        upload_id = uploader.upload(job)
        print(f"Uploaded YouTube video ID: {upload_id}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
