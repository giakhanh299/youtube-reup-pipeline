from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from processors.sheet_upload_processor import SheetUploadProcessor


class FakeSheetRepository:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    def load_upload_jobs(self, worksheet_name: str):
        self.loaded_worksheet_name = worksheet_name
        return self.rows

    def update_upload_result(
        self,
        worksheet_name: str,
        row_number: int,
        upload_status: str,
        youtube_video_id: str = "",
        upload_error: str = "",
        upload_time: str = "",
    ) -> None:
        self.updates.append(
            {
                "worksheet_name": worksheet_name,
                "row_number": row_number,
                "upload_status": upload_status,
                "youtube_video_id": youtube_video_id,
                "upload_error": upload_error,
                "upload_time": upload_time,
            }
        )


class FakeUploader:
    def __init__(self):
        self.jobs = []

    def upload(self, job):
        self.jobs.append(job)
        return "yt123"


class FailingUploader:
    def upload(self, job):
        raise RuntimeError("upload failed")


class SheetUploadProcessorTests(unittest.TestCase):
    def test_uploads_pending_rows_and_writes_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "video.mp4"
            video.write_bytes(b"fake")
            repository = FakeSheetRepository(
                [
                    (
                        2,
                        {
                            "video_path": str(video),
                            "title": "Title",
                            "description": "Desc",
                            "tags": "a,b",
                            "categoryId": "",
                            "privacyStatus": "",
                            "upload_status": "pending",
                        },
                    )
                ]
            )
            uploader = FakeUploader()

            results = SheetUploadProcessor(repository, uploader).process(
                {
                    "upload_sheet_name": "Video đã edit",
                    "youtube_default_privacy": "private",
                    "youtube_default_category_id": "22",
                    "upload_status_new": "pending",
                    "upload_status_uploading": "uploading",
                    "upload_status_done": "uploaded",
                    "upload_status_error": "failed",
                }
            )

        self.assertEqual(repository.loaded_worksheet_name, "Video đã edit")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].youtube_video_id, "yt123")
        self.assertEqual(uploader.jobs[0].privacy_status, "private")
        self.assertEqual(uploader.jobs[0].category_id, "22")
        self.assertEqual(uploader.jobs[0].tags, ["a", "b"])
        self.assertEqual(repository.updates[0]["upload_status"], "uploading")
        self.assertEqual(repository.updates[1]["upload_status"], "uploaded")
        self.assertEqual(repository.updates[1]["youtube_video_id"], "yt123")
        self.assertTrue(repository.updates[1]["upload_time"])

    def test_skips_non_pending_rows(self) -> None:
        repository = FakeSheetRepository([(2, {"upload_status": "uploaded", "video_path": "x.mp4"})])
        uploader = FakeUploader()

        results = SheetUploadProcessor(repository, uploader).process({"upload_status_new": "pending"})

        self.assertEqual(results, [])
        self.assertEqual(repository.updates, [])
        self.assertEqual(uploader.jobs, [])

    def test_writes_failed_status_and_error(self) -> None:
        repository = FakeSheetRepository([(2, {"upload_status": "pending", "video_path": "missing.mp4"})])

        results = SheetUploadProcessor(repository, FailingUploader()).process(
            {
                "upload_status_new": "pending",
                "upload_status_error": "failed",
            }
        )

        self.assertEqual(results[0].status, "failed")
        self.assertIn("video_path not found", results[0].error)
        self.assertEqual(repository.updates[0]["upload_status"], "failed")
        self.assertIn("video_path not found", repository.updates[0]["upload_error"])


if __name__ == "__main__":
    unittest.main()
