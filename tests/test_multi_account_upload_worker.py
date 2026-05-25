from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from repositories.queue_persistence import QueueJobState
from services.active_channel_state import ActiveChannelStateStore
from services.channel_sheet_registry import ChannelSheetConfig
from workers.multi_account_upload_worker import MultiAccountUploader


class FakeAccountUploader:
    def __init__(self, settings: dict):
        self.settings = settings
        self.jobs = []

    def upload(self, job: QueueJobState) -> str:
        self.jobs.append(job)
        return f"yt-{job.account_name or job.channel_key or 'default'}"


class MultiAccountUploaderTests(unittest.TestCase):
    def setUp(self) -> None:
        base = Path.home() / ".codex" / "memories"
        if not base.exists():
            base = Path(tempfile.gettempdir())
        self.root = base / f"test_multi_account_{uuid.uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

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

    def test_uses_active_channel_token_when_job_has_no_token(self) -> None:
        created = []
        settings = {
            "youtube_oauth_token_json": "default.pickle",
            "active_channel_lock_path": str(self.root / "runtime" / "state" / "active_channel.lock"),
            "active_channel_state_path": str(self.root / "runtime" / "state" / "active_channel.json"),
        }
        channel = ChannelSheetConfig(
            channel_id="channel_a",
            channel_name="Channel A",
            input_folder="legacy/input",
            output_folder="legacy/output",
            voice_id="",
            voice_name="",
            voice_path="",
            youtube_oauth_token_json="token_a.pickle",
            enabled=True,
        )
        store = ActiveChannelStateStore(self.root, settings)
        store.select(channel, clean_before_start=False)
        router = MultiAccountUploader(settings, lambda account_settings: created.append(FakeAccountUploader(account_settings)) or created[-1])

        router.upload(QueueJobState(job_id="job_1", status="READY_UPLOAD", channel_key="channel_a"))

        self.assertEqual(created[0].settings["youtube_oauth_token_json"], "token_a.pickle")
        self.assertNotEqual(created[0].settings["youtube_oauth_token_json"], "token_b.pickle")
        store.finish(clean_after_finish=False)


if __name__ == "__main__":
    unittest.main()
