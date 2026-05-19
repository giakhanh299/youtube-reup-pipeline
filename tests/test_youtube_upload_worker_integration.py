from __future__ import annotations

import tempfile
import unittest

from integrations.youtube.youtube_api_uploader import UploadState
from repositories.queue_persistence import JsonQueuePersistence, QueueJobState
from workers.upload_worker import UploadWorker, build_youtube_upload_worker


class RecordingUploadClient:
    def upload(self, job: QueueJobState) -> str:
        return f"yt-{job.job_id}"


class YouTubeUploadWorkerIntegrationTests(unittest.TestCase):
    def test_worker_records_upload_lifecycle_state_without_breaking_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            persistence = JsonQueuePersistence(temp)
            worker = UploadWorker(RecordingUploadClient(), persistence)

            result = worker.process_one(QueueJobState(job_id="job_1", status="READY_UPLOAD"))
            saved = persistence.load_job_state("job_1")

        self.assertEqual(result.status, "UPLOADED")
        self.assertEqual(saved.status, "UPLOADED")
        self.assertEqual(saved.upload_state, UploadState.UPLOADED)

    def test_youtube_worker_builder_wires_state_callback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            persistence = JsonQueuePersistence(temp)
            worker = build_youtube_upload_worker(
                {
                    "youtube_oauth_credentials_json": "oauth.json",
                    "youtube_oauth_token_json": "token.json",
                },
                persistence,
            )
            job = QueueJobState(job_id="job_1", status="READY_UPLOAD")
            worker.upload_client.state_callback(UploadState.RETRYING, job)  # type: ignore[attr-defined]
            retrying = persistence.load_job_state("job_1")
            worker.upload_client.upload = lambda job: "yt-job_1"  # type: ignore[method-assign]

            result = worker.process_one(job)
            saved = persistence.load_job_state("job_1")

        self.assertEqual(result.upload_id, "yt-job_1")
        self.assertEqual(retrying.status, "UPLOADING")
        self.assertEqual(retrying.upload_state, UploadState.RETRYING)
        self.assertEqual(saved.status, "UPLOADED")
        self.assertEqual(saved.upload_state, UploadState.UPLOADED)


if __name__ == "__main__":
    unittest.main()
