from __future__ import annotations

import unittest
import tempfile

from repositories.queue_persistence import JsonQueuePersistence, NullQueuePersistence, QueueJobState


class QueuePersistenceTests(unittest.TestCase):
    def test_null_queue_persistence_is_noop(self) -> None:
        persistence = NullQueuePersistence()
        state = QueueJobState(job_id="job_1", status="PROCESSING")

        persistence.save_job_state(state)
        persistence.mark_failed("job_1", "error")

        self.assertIsNone(persistence.load_job_state("job_1"))

    def test_json_queue_persistence_saves_loads_and_marks_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            persistence = JsonQueuePersistence(temp)
            state = QueueJobState(
                job_id="job/1",
                status="PROCESSING",
                channel_id="kenh_1",
                channel_key="main",
                account_name="account_a",
                youtube_token_path="token_a.pickle",
            )

            persistence.save_job_state(state)
            loaded = persistence.load_job_state("job/1")
            persistence.mark_failed("job/1", "boom")
            failed = persistence.load_job_state("job/1")

        self.assertEqual(loaded, state)
        self.assertIsNotNone(failed)
        self.assertEqual(failed.status, "ERROR")
        self.assertEqual(failed.error, "boom")
        self.assertEqual(failed.retry_count, 1)
        self.assertEqual(failed.channel_key, "main")
        self.assertEqual(failed.account_name, "account_a")
        self.assertEqual(failed.youtube_token_path, "token_a.pickle")


if __name__ == "__main__":
    unittest.main()
