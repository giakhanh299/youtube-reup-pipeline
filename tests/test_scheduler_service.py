from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from services.scheduler_service import QueueAutomationScheduler, SchedulerDaemon, SchedulerLock, SchedulerTask


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class FakeLogger:
    def __init__(self):
        self.worker_events = []
        self.error_events = []

    def worker(self, event: str, **fields) -> None:
        self.worker_events.append((event, fields))

    def error(self, event: str, **fields) -> None:
        self.error_events.append((event, fields))

    def scheduler(self, event: str, **fields) -> None:
        self.worker_events.append((event, fields))


class FakeQueueRepository:
    def __init__(self, queue):
        self.queue = queue
        self.updates = []
        self.channels = {"kenh_1": {"output_folder": "runtime/out", "voice_id": "voice_1"}}
        self.voices = {"voice_1": {"active": True}}

    def load_all(self):
        return None, self.channels, self.voices, {}, {}, {}, self.queue

    def merge_pack_into_channel(self, channel, music_packs, overlay_packs, render_presets):
        return dict(channel)

    def update_status_by_job_id(self, job_id, status, output_path="", error="", youtube_video_id="", upload_time=""):
        self.updates.append(
            {
                "job_id": job_id,
                "status": status,
                "output_path": output_path,
                "error": error,
                "youtube_video_id": youtube_video_id,
                "upload_time": upload_time,
            }
        )


class FakeJobProcessor:
    def process_one_video(self, video, text_file, channel_id, channel_cfg, voices, settings):
        return f"rendered/{video.name}"


class FakeUploader:
    def __init__(self):
        self.jobs = []

    def upload(self, job):
        self.jobs.append(job)
        return f"yt-{job.job_id}"


class SchedulerServiceTests(unittest.TestCase):
    def test_runs_due_tasks_on_interval(self) -> None:
        clock = FakeClock()
        calls = []
        task = SchedulerTask("task", 2, lambda: calls.append(clock.value) or [1])
        scheduler = SchedulerDaemon([task], sleep=clock.sleep, clock=clock, heartbeat_interval_seconds=100)

        snapshot = scheduler.run(max_cycles=5)

        self.assertEqual(calls, [0.0, 2.0, 4.0])
        self.assertEqual(snapshot.task_stats["task"]["run_count"], 3)
        self.assertEqual(snapshot.task_stats["task"]["last_result_count"], 1)

    def test_failed_task_uses_retry_interval(self) -> None:
        clock = FakeClock()
        calls = []

        def action():
            calls.append(clock.value)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return []

        task = SchedulerTask("task", 10, action, retry_interval_seconds=2)
        logger = FakeLogger()
        scheduler = SchedulerDaemon([task], sleep=clock.sleep, clock=clock, heartbeat_interval_seconds=100, logger=logger)

        snapshot = scheduler.run(max_cycles=4)

        self.assertEqual(calls, [0.0, 2.0])
        self.assertEqual(snapshot.task_stats["task"]["error_count"], 1)
        self.assertEqual(logger.error_events[0][0], "scheduler_task_failed")

    def test_writes_heartbeat(self) -> None:
        clock = FakeClock()
        logger = FakeLogger()
        task = SchedulerTask("task", 10, lambda: [])
        scheduler = SchedulerDaemon([task], sleep=clock.sleep, clock=clock, heartbeat_interval_seconds=2, logger=logger)

        scheduler.run(max_cycles=4)

        heartbeat_events = [event for event, _fields in logger.worker_events if event == "scheduler_heartbeat"]
        self.assertEqual(len(heartbeat_events), 2)

    def test_queue_scheduler_renders_new_jobs_and_updates_statuses(self) -> None:
        repository = FakeQueueRepository(
            [{"job_id": "job_1", "status": "NEW", "channel_id": "kenh_1", "video_path": "a.mp4", "text_path": "a.srt"}]
        )
        scheduler = QueueAutomationScheduler(repository, FakeJobProcessor(), FakeUploader(), {})

        processed = scheduler.render_cycle()

        self.assertEqual(processed, 1)
        self.assertEqual(repository.updates[0]["status"], "PROCESSING")
        self.assertEqual(repository.updates[1]["status"], "READY_UPLOAD")
        self.assertEqual(repository.updates[1]["output_path"], "rendered/a.mp4")
        self.assertEqual(scheduler.stats.processed_count, 1)

    def test_queue_scheduler_uploads_ready_jobs_and_records_video_id(self) -> None:
        uploader = FakeUploader()
        repository = FakeQueueRepository(
            [{"job_id": "job_1", "status": "READY_UPLOAD", "output_path": "out.mp4", "title": "Title"}]
        )
        scheduler = QueueAutomationScheduler(repository, FakeJobProcessor(), uploader, {"queue_status_uploaded": "UPLOADED"})

        uploaded = scheduler.upload_cycle()

        self.assertEqual(uploaded, 1)
        self.assertEqual(repository.updates[0]["status"], "UPLOADED")
        self.assertEqual(repository.updates[0]["youtube_video_id"], "yt-job_1")
        self.assertEqual(scheduler.stats.uploaded_count, 1)

    def test_queue_scheduler_skips_ready_jobs_with_existing_youtube_id(self) -> None:
        uploader = FakeUploader()
        repository = FakeQueueRepository(
            [{"job_id": "job_1", "status": "READY_UPLOAD", "output_path": "out.mp4", "youtube_video_id": "existing"}]
        )
        scheduler = QueueAutomationScheduler(repository, FakeJobProcessor(), uploader, {})

        uploaded = scheduler.upload_cycle()

        self.assertEqual(uploaded, 0)
        self.assertEqual(uploader.jobs, [])
        self.assertEqual(scheduler.stats.skipped_count, 1)

    def test_queue_scheduler_recovers_stale_processing_jobs(self) -> None:
        repository = FakeQueueRepository(
            [{"job_id": "job_1", "status": "PROCESSING", "processing_started_at": "2020-01-01T00:00:00+00:00"}]
        )
        scheduler = QueueAutomationScheduler(
            repository,
            FakeJobProcessor(),
            FakeUploader(),
            {"scheduler_processing_stale_after_seconds": 1},
            clock=lambda: 1893456000.0,
        )

        recovered = scheduler.recover_stale_processing(repository.queue)

        self.assertEqual(recovered, 1)
        self.assertEqual(repository.updates[0]["status"], "NEW")
        self.assertEqual(scheduler.stats.recovered_count, 1)

    def test_scheduler_lock_prevents_duplicate_local_instances(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            lock_path = Path(temp) / "scheduler.lock"
            first = SchedulerLock(lock_path)
            second = SchedulerLock(lock_path)

            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()
            self.assertTrue(second.acquire())
            second.release()


if __name__ == "__main__":
    unittest.main()
