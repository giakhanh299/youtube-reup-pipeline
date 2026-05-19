from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import pickle

from logs.structured_logger import NullLogger
from repositories.queue_persistence import QueueJobState
from utils.retry import RetryStrategy


YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


class UploadState:
    PENDING = "pending"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass(frozen=True)
class YouTubeUploadMetadata:
    title: str
    description: str = ""
    tags: list[str] | None = None
    category_id: str = "22"
    privacy_status: str = "private"


def parse_tags(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


class YouTubeApiUploader:
    """YouTube Data API v3 resumable uploader.

    The Google API client is injectable so tests can use mocks and never perform
    real uploads. If no client is supplied, credentials are loaded lazily when
    upload() is called.
    """

    def __init__(
        self,
        client: Any = None,
        credentials_path: str = "",
        token_path: str = "",
        chunk_size: int = -1,
        retry_strategy: RetryStrategy | None = None,
        logger: Any = None,
        state_callback: Callable[[str, QueueJobState], None] | None = None,
        media_upload_factory: Callable[..., Any] | None = None,
        progress_callback: Callable[[float], None] | None = None,
    ):
        self.client = client
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.chunk_size = chunk_size
        self.retry_strategy = retry_strategy
        self.logger = logger or NullLogger()
        self.state_callback = state_callback
        self.media_upload_factory = media_upload_factory
        self.progress_callback = progress_callback

    @classmethod
    def from_settings(
        cls,
        settings: dict,
        retry_strategy: RetryStrategy | None = None,
        logger: Any = None,
        state_callback: Callable[[str, QueueJobState], None] | None = None,
    ) -> "YouTubeApiUploader":
        return cls(
            credentials_path=settings.get("youtube_oauth_credentials_json", ""),
            token_path=settings.get("youtube_oauth_token_json") or settings.get("youtube_token_pickle_path", ""),
            chunk_size=int(settings.get("youtube_upload_chunk_size", -1)),
            retry_strategy=retry_strategy,
            logger=logger,
            state_callback=state_callback,
        )

    def _set_state(self, state: str, job: QueueJobState) -> None:
        self.logger.upload("youtube_upload_state", job_id=job.job_id, state=state)
        if self.state_callback:
            self.state_callback(state, job)

    def _build_client(self) -> Any:
        if self.client is not None:
            return self.client
        if not self.credentials_path:
            raise ValueError("youtube_oauth_credentials_json is required")
        if not self.token_path:
            raise ValueError("youtube_oauth_token_json is required")

        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        token = Path(self.token_path)
        credentials = None
        if token.exists():
            if token.suffix.lower() == ".pickle":
                with token.open("rb") as handle:
                    credentials = pickle.load(handle)
            else:
                credentials = Credentials.from_authorized_user_file(str(token), [YOUTUBE_UPLOAD_SCOPE])
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, [YOUTUBE_UPLOAD_SCOPE])
                credentials = flow.run_local_server(port=0)
            token.parent.mkdir(parents=True, exist_ok=True)
            if token.suffix.lower() == ".pickle":
                with token.open("wb") as handle:
                    pickle.dump(credentials, handle)
            else:
                token.write_text(credentials.to_json(), encoding="utf-8")

        self.client = build("youtube", "v3", credentials=credentials)
        return self.client

    def _metadata_for(self, job: QueueJobState) -> YouTubeUploadMetadata:
        video_path = Path(job.output_path or job.video_path)
        title = job.title.strip() if job.title else video_path.stem
        if not title:
            raise ValueError("YouTube upload title is required")
        privacy_status = (job.privacy_status or "private").strip() or "private"
        category_id = (job.category_id or "22").strip() or "22"
        return YouTubeUploadMetadata(
            title=title,
            description=job.description or "",
            tags=parse_tags(job.tags),
            category_id=category_id,
            privacy_status=privacy_status,
        )

    def _upload_once(self, job: QueueJobState) -> str:
        video_path = Path(job.output_path or job.video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"upload video not found: {video_path}")

        metadata = self._metadata_for(job)
        client = self._build_client()

        media_upload_factory = self.media_upload_factory
        if media_upload_factory is None:
            from googleapiclient.http import MediaFileUpload

            media_upload_factory = MediaFileUpload

        body = {
            "snippet": {
                "title": metadata.title,
                "description": metadata.description,
                "tags": metadata.tags or [],
                "categoryId": metadata.category_id,
            },
            "status": {"privacyStatus": metadata.privacy_status},
        }
        media = media_upload_factory(str(video_path), chunksize=self.chunk_size, resumable=True)
        request = client.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status is not None and self.progress_callback:
                progress = getattr(status, "progress", None)
                if callable(progress):
                    self.progress_callback(float(progress()))
        upload_id = str(response.get("id", "")).strip()
        if not upload_id:
            raise RuntimeError("YouTube API upload response did not include video id")
        return upload_id

    def upload(self, job: QueueJobState) -> str:
        self._set_state(UploadState.PENDING, job)
        try:
            self._set_state(UploadState.UPLOADING, job)
            if not self.retry_strategy:
                upload_id = self._upload_once(job)
            else:
                retrying = {"value": False}

                def _attempt() -> str:
                    try:
                        return self._upload_once(job)
                    except Exception:
                        if not retrying["value"]:
                            self._set_state(UploadState.RETRYING, job)
                            retrying["value"] = True
                        raise

                upload_id = self.retry_strategy.run(
                    _attempt,
                    "youtube_resumable_upload",
                    "youtube_api",
                )
            self._set_state(UploadState.UPLOADED, job)
            return upload_id
        except Exception:
            self._set_state(UploadState.FAILED, job)
            raise
