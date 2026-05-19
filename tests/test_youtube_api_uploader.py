from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from integrations.youtube.youtube_api_uploader import UploadState, YouTubeApiUploader, parse_tags
from repositories.queue_persistence import QueueJobState
from utils.retry import RetryStrategy


class FakeRequest:
    def __init__(self, response: dict, statuses=None):
        self.response = response
        self.statuses = list(statuses or [])
        self.calls = 0

    def next_chunk(self):
        self.calls += 1
        if self.statuses:
            return self.statuses.pop(0), None
        return None, self.response


class FakeStatus:
    def __init__(self, value: float):
        self.value = value

    def progress(self) -> float:
        return self.value


class FakeVideos:
    def __init__(self, request: FakeRequest):
        self.request = request
        self.insert_kwargs = None

    def insert(self, **kwargs):
        self.insert_kwargs = kwargs
        return self.request


class FakeClient:
    def __init__(self, request: FakeRequest):
        self.fake_videos = FakeVideos(request)

    def videos(self):
        return self.fake_videos


class FakeMediaFileUpload:
    def __init__(self, filename: str, chunksize: int, resumable: bool):
        self.filename = filename
        self.chunksize = chunksize
        self.resumable = resumable


class YouTubeApiUploaderTests(unittest.TestCase):
    def test_parse_tags_accepts_csv_and_lists(self) -> None:
        self.assertEqual(parse_tags("one, two,,three"), ["one", "two", "three"])
        self.assertEqual(parse_tags(["one", " ", "two"]), ["one", "two"])

    def test_upload_uses_resumable_api_and_defaults_private(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "ready.mp4"
            video.write_bytes(b"fake video")
            request = FakeRequest({"id": "yt123"})
            client = FakeClient(request)
            states = []
            uploader = YouTubeApiUploader(
                client=client,
                chunk_size=1024,
                state_callback=lambda state, _job: states.append(state),
                media_upload_factory=FakeMediaFileUpload,
            )

            upload_id = uploader.upload(
                QueueJobState(
                    job_id="job_1",
                    status="READY_UPLOAD",
                    output_path=str(video),
                    title="My title",
                    description="My description",
                    tags=["tag1", "tag2"],
                )
            )

        kwargs = client.fake_videos.insert_kwargs
        self.assertEqual(upload_id, "yt123")
        self.assertEqual(kwargs["part"], "snippet,status")
        self.assertEqual(kwargs["body"]["snippet"]["title"], "My title")
        self.assertEqual(kwargs["body"]["snippet"]["tags"], ["tag1", "tag2"])
        self.assertEqual(kwargs["body"]["snippet"]["categoryId"], "22")
        self.assertEqual(kwargs["body"]["status"]["privacyStatus"], "private")
        self.assertTrue(kwargs["media_body"].resumable)
        self.assertEqual(states, [UploadState.PENDING, UploadState.UPLOADING, UploadState.UPLOADED])

    def test_upload_retries_api_failures_with_mocked_client(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "ready.mp4"
            video.write_bytes(b"fake video")
            attempts = {"count": 0}
            uploader = YouTubeApiUploader(
                client=FakeClient(FakeRequest({"id": "yt123"})),
                retry_strategy=RetryStrategy(max_attempts=2, base_delay=0, sleep=lambda _delay: None),
                media_upload_factory=FakeMediaFileUpload,
            )

            def flaky(job: QueueJobState) -> str:
                attempts["count"] += 1
                if attempts["count"] == 1:
                    raise RuntimeError("temporary API failure")
                return "yt123"

            uploader._upload_once = flaky  # type: ignore[method-assign]

            upload_id = uploader.upload(QueueJobState(job_id="job_1", status="READY_UPLOAD", output_path=str(video)))

        self.assertEqual(upload_id, "yt123")
        self.assertEqual(attempts["count"], 2)

    def test_upload_reports_chunk_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "ready.mp4"
            video.write_bytes(b"fake video")
            progress = []
            request = FakeRequest({"id": "yt123"}, statuses=[FakeStatus(0.25), FakeStatus(0.75)])
            uploader = YouTubeApiUploader(
                client=FakeClient(request),
                media_upload_factory=FakeMediaFileUpload,
                progress_callback=progress.append,
            )

            upload_id = uploader.upload(QueueJobState(job_id="job_1", status="READY_UPLOAD", output_path=str(video)))

        self.assertEqual(upload_id, "yt123")
        self.assertEqual(progress, [0.25, 0.75])


if __name__ == "__main__":
    unittest.main()
