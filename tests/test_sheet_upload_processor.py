from __future__ import annotations

from pathlib import Path
import time
import tempfile
import unittest

from processors.sheet_upload_processor import SheetUploadProcessor


class FakeSheetRepository:
    def __init__(self, rows, channel_configs=None):
        self.rows = rows
        self.channel_configs = channel_configs
        self.updates = []

    def load_upload_jobs(self, worksheet_name: str):
        self.loaded_worksheet_name = worksheet_name
        return self.rows

    def load_upload_channel_configs(self, worksheet_name: str = "Channel Config"):
        self.loaded_channel_config_sheet_name = worksheet_name
        if self.channel_configs is None:
            raise RuntimeError("no channel config")
        return self.channel_configs

    def update_upload_result(
        self,
        worksheet_name: str,
        row_number: int,
        upload_status: str,
        youtube_video_id: str = "",
        upload_error: str = "",
        upload_time: str = "",
        retry_count=None,
        last_error: str = "",
        upload_started_at: str = "",
        upload_finished_at: str = "",
    ) -> None:
        self.updates.append(
            {
                "worksheet_name": worksheet_name,
                "row_number": row_number,
                "upload_status": upload_status,
                "youtube_video_id": youtube_video_id,
                "upload_error": upload_error,
                "upload_time": upload_time,
                "retry_count": retry_count,
                "last_error": last_error,
                "upload_started_at": upload_started_at,
                "upload_finished_at": upload_finished_at,
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


class SlowUploader:
    def upload(self, job):
        time.sleep(0.2)
        return "yt-slow"


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
        self.assertTrue(repository.updates[0]["upload_started_at"])
        self.assertEqual(repository.updates[1]["upload_status"], "uploaded")
        self.assertEqual(repository.updates[1]["youtube_video_id"], "yt123")
        self.assertTrue(repository.updates[1]["upload_time"])
        self.assertTrue(repository.updates[1]["upload_finished_at"])

    def test_skips_non_pending_rows(self) -> None:
        repository = FakeSheetRepository([(2, {"upload_status": "uploaded", "video_path": "x.mp4"})])
        uploader = FakeUploader()

        results = SheetUploadProcessor(repository, uploader).process({"upload_status_new": "pending"})

        self.assertEqual(results, [])
        self.assertEqual(repository.updates, [])
        self.assertEqual(uploader.jobs, [])

    def test_applies_channel_defaults_when_channel_key_is_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "clip.mp4"
            video.write_bytes(b"fake")
            repository = FakeSheetRepository(
                [(2, {"video_path": str(video), "channel_key": "main", "upload_status": "pending"})],
                {
                    "main": {
                        "channel_key": "main",
                        "channel_name": "Main Channel",
                        "account_name": "default",
                        "default_privacyStatus": "private",
                        "default_categoryId": "24",
                        "tags_default": "douyin,reup",
                        "title_template": "{channel_name} - {stem}",
                        "description_template": "Uploaded for {channel_name}",
                    }
                },
            )
            uploader = FakeUploader()

            SheetUploadProcessor(repository, uploader).process(
                {
                    "upload_sheet_name": "Upload Queue",
                    "channel_config_sheet_name": "Channel Config",
                    "upload_status_new": "pending",
                }
            )

        self.assertEqual(repository.loaded_channel_config_sheet_name, "Channel Config")
        self.assertEqual(uploader.jobs[0].privacy_status, "private")
        self.assertEqual(uploader.jobs[0].category_id, "24")
        self.assertEqual(uploader.jobs[0].tags, ["douyin", "reup"])
        self.assertEqual(uploader.jobs[0].title, "Main Channel - clip")
        self.assertEqual(uploader.jobs[0].description, "Uploaded for Main Channel")
        self.assertEqual(uploader.jobs[0].channel_key, "main")
        self.assertEqual(uploader.jobs[0].account_name, "default")

    def test_missing_channel_key_config_fails_readably(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "clip.mp4"
            video.write_bytes(b"fake")
            repository = FakeSheetRepository(
                [(2, {"video_path": str(video), "channel_key": "missing", "upload_status": "pending"})],
                {"main": {"channel_key": "main"}},
            )

            results = SheetUploadProcessor(repository, FakeUploader()).process({"upload_status_new": "pending"})

        self.assertEqual(results[0].status, "failed")
        self.assertIn("channel_key not found or disabled", results[0].error)

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
        self.assertEqual(repository.updates[0]["retry_count"], 1)
        self.assertIn("video_path not found", repository.updates[0]["last_error"])
        self.assertIn("video_path not found", repository.updates[0]["upload_error"])

    def test_skips_rows_with_youtube_video_id_to_prevent_duplicate_uploads(self) -> None:
        repository = FakeSheetRepository(
            [(2, {"upload_status": "pending", "youtube_video_id": "yt_existing", "video_path": "x.mp4"})]
        )
        uploader = FakeUploader()

        results = SheetUploadProcessor(repository, uploader).process({"upload_status_new": "pending"})

        self.assertEqual(results, [])
        self.assertEqual(repository.updates, [])
        self.assertEqual(uploader.jobs, [])

    def test_retries_failed_rows_until_max_retry_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "video.mp4"
            video.write_bytes(b"fake")
            repository = FakeSheetRepository(
                [
                    (
                        2,
                        {
                            "video_path": str(video),
                            "upload_status": "failed",
                            "retry_count": "1",
                        },
                    )
                ]
            )
            uploader = FakeUploader()

            results = SheetUploadProcessor(repository, uploader).process(
                {"upload_status_error": "failed", "upload_retry_max_attempts": 3}
            )

        self.assertEqual(results[0].status, "uploaded")
        self.assertEqual(len(uploader.jobs), 1)

    def test_skips_failed_rows_at_retry_limit(self) -> None:
        repository = FakeSheetRepository(
            [(2, {"video_path": "x.mp4", "upload_status": "failed", "retry_count": "3"})]
        )
        uploader = FakeUploader()

        results = SheetUploadProcessor(repository, uploader).process(
            {"upload_status_error": "failed", "upload_retry_max_attempts": 3}
        )

        self.assertEqual(results, [])
        self.assertEqual(uploader.jobs, [])

    def test_recovers_stale_uploading_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "video.mp4"
            video.write_bytes(b"fake")
            repository = FakeSheetRepository(
                [
                    (
                        2,
                        {
                            "video_path": str(video),
                            "upload_status": "uploading",
                            "upload_started_at": "2020-01-01T00:00:00+00:00",
                        },
                    )
                ]
            )
            uploader = FakeUploader()

            results = SheetUploadProcessor(repository, uploader).process(
                {
                    "upload_status_uploading": "uploading",
                    "upload_recover_stale_after_seconds": 1,
                }
            )

        self.assertEqual(results[0].status, "uploaded")
        self.assertEqual(len(uploader.jobs), 1)

    def test_skips_fresh_uploading_rows(self) -> None:
        repository = FakeSheetRepository(
            [
                (
                    2,
                    {
                        "video_path": "x.mp4",
                        "upload_status": "uploading",
                        "upload_started_at": "2999-01-01T00:00:00+00:00",
                    },
                )
            ]
        )
        uploader = FakeUploader()

        results = SheetUploadProcessor(repository, uploader).process(
            {
                "upload_status_uploading": "uploading",
                "upload_recover_stale_after_seconds": 3600,
            }
        )

        self.assertEqual(results, [])
        self.assertEqual(uploader.jobs, [])

    def test_rejects_unsupported_file_extensions_before_upload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "video.txt"
            video.write_text("not video", encoding="utf-8")
            repository = FakeSheetRepository([(2, {"upload_status": "pending", "video_path": str(video)})])
            uploader = FakeUploader()

            results = SheetUploadProcessor(repository, uploader).process(
                {"upload_status_new": "pending", "upload_allowed_exts": [".mp4"]}
            )

        self.assertIn("unsupported upload file extension", results[0].error)
        self.assertEqual(uploader.jobs, [])

    def test_upload_timeout_writes_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "video.mp4"
            video.write_bytes(b"fake")
            repository = FakeSheetRepository([(2, {"upload_status": "pending", "video_path": str(video)})])

            results = SheetUploadProcessor(repository, SlowUploader()).process(
                {"upload_status_new": "pending", "upload_timeout_seconds": 0.01}
            )

        self.assertEqual(results[0].status, "failed")
        self.assertIn("upload timed out", results[0].error)


if __name__ == "__main__":
    unittest.main()
