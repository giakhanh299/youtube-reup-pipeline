from __future__ import annotations

import tempfile
import unittest

from repositories.queue_persistence import JsonQueuePersistence, QueueJobState
from workers.upload_worker import UploadWorker


class FakeUploadClient:
    def upload(self, job: QueueJobState) -> str:
        return f"upload-{job.job_id}"


class FakeLedgerRepository:
    def __init__(self):
        self.rows = []

    def upsert_uploaded_video(self, row):
        self.rows.append(row)
        return "appended"


class UploadWorkerTests(unittest.TestCase):
    def test_worker_skips_when_upload_client_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            worker = UploadWorker(None, JsonQueuePersistence(temp))

            result = worker.process_one(QueueJobState(job_id="job_1", status="READY_UPLOAD"))

        self.assertEqual(result.status, "SKIPPED")

    def test_worker_processes_ready_job_with_client(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            persistence = JsonQueuePersistence(temp)
            worker = UploadWorker(FakeUploadClient(), persistence)
            job = QueueJobState(job_id="job_1", status="READY_UPLOAD", channel_id="kenh_1")

            result = worker.process_one(job)
            saved = persistence.load_job_state("job_1")

        self.assertEqual(result.status, "UPLOADED")
        self.assertEqual(result.upload_id, "upload-job_1")
        self.assertEqual(saved.status, "UPLOADED")

    def test_worker_writes_uploaded_ledger_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            persistence = JsonQueuePersistence(temp)
            ledger = FakeLedgerRepository()
            worker = UploadWorker(FakeUploadClient(), persistence, ledger_repository=ledger)
            job = QueueJobState(
                job_id="job_1",
                status="READY_UPLOAD",
                channel_id="kenh_1",
                output_path="out.mp4",
                title="Title",
                description="Desc",
                tags=["a", "b"],
                category_id="22",
                privacy_status="private",
            )

            result = worker.process_one(job)

        self.assertEqual(result.status, "UPLOADED")
        self.assertEqual(ledger.rows[0]["job_id"], "job_1")
        self.assertEqual(ledger.rows[0]["youtube_video_id"], "upload-job_1")
        self.assertEqual(ledger.rows[0]["youtube_url"], "https://www.youtube.com/watch?v=upload-job_1")


if __name__ == "__main__":
    unittest.main()
