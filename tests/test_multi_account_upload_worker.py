from __future__ import annotations

import unittest

from repositories.queue_persistence import QueueJobState
from workers.multi_account_upload_worker import MultiAccountUploader


class FakeAccountUploader:
    def __init__(self, settings: dict):
        self.settings = settings
        self.jobs = []

    def upload(self, job: QueueJobState) -> str:
        self.jobs.append(job)
        return f"yt-{job.account_name or job.channel_key or 'default'}"


class MultiAccountUploaderTests(unittest.TestCase):
    def test_routes_jobs_to_separate_account_uploaders(self) -> None:
        created = []

        def factory(settings):
            uploader = FakeAccountUploader(settings)
            created.append(uploader)
            return uploader

        router = MultiAccountUploader({"youtube_oauth_token_json": "default.json", "upload_worker_count": 2}, factory)

        first = router.upload(
            QueueJobState(
                job_id="job_1",
                status="READY_UPLOAD",
                account_name="account_a",
                youtube_token_path="token_a.pickle",
            )
        )
        second = router.upload(
            QueueJobState(
                job_id="job_2",
                status="READY_UPLOAD",
                account_name="account_b",
                youtube_token_path="token_b.pickle",
            )
        )

        self.assertEqual(first, "yt-account_a")
        self.assertEqual(second, "yt-account_b")
        self.assertEqual(len(created), 2)
        self.assertEqual(created[0].settings["youtube_oauth_token_json"], "token_a.pickle")
        self.assertEqual(created[1].settings["youtube_oauth_token_json"], "token_b.pickle")

    def test_reuses_same_uploader_for_same_account(self) -> None:
        created = []
        router = MultiAccountUploader({}, lambda settings: created.append(FakeAccountUploader(settings)) or created[-1])

        router.upload(QueueJobState(job_id="job_1", status="READY_UPLOAD", account_name="account_a", youtube_token_path="a.pickle"))
        router.upload(QueueJobState(job_id="job_2", status="READY_UPLOAD", account_name="account_a", youtube_token_path="a.pickle"))

        self.assertEqual(len(created), 1)
        self.assertEqual(len(created[0].jobs), 2)

    def test_prevents_token_conflict_for_same_account(self) -> None:
        router = MultiAccountUploader({}, lambda settings: FakeAccountUploader(settings))

        router.upload(QueueJobState(job_id="job_1", status="READY_UPLOAD", account_name="account_a", youtube_token_path="a.pickle"))

        with self.assertRaisesRegex(ValueError, "token path conflict"):
            router.upload(
                QueueJobState(
                    job_id="job_2",
                    status="READY_UPLOAD",
                    account_name="account_a",
                    youtube_token_path="other.pickle",
                )
            )

    def test_defaults_to_single_account_for_backward_compatibility(self) -> None:
        created = []
        router = MultiAccountUploader({"youtube_oauth_token_json": "default.pickle"}, lambda settings: created.append(FakeAccountUploader(settings)) or created[-1])

        upload_id = router.upload(QueueJobState(job_id="job_1", status="READY_UPLOAD"))

        self.assertEqual(upload_id, "yt-default")
        self.assertEqual(created[0].settings["youtube_oauth_token_json"], "default.pickle")


if __name__ == "__main__":
    unittest.main()
