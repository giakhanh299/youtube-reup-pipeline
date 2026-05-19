from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from services.dashboard_service import DashboardControlStore, DashboardStateBuilder


class DashboardServiceTests(unittest.TestCase):
    def test_snapshot_counts_jobs_accounts_retries_and_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            queue_dir = root / "runtime" / "state" / "queue"
            log_dir = root / "runtime" / "logs"
            queue_dir.mkdir(parents=True)
            log_dir.mkdir(parents=True)
            (queue_dir / "job1.json").write_text(
                json.dumps({"job_id": "job1", "status": "pending", "account_name": "a", "retry_count": 1}),
                encoding="utf-8",
            )
            (queue_dir / "job2.json").write_text(
                json.dumps({"job_id": "job2", "upload_state": "uploaded", "channel_key": "main"}),
                encoding="utf-8",
            )
            (log_dir / "upload.log").write_text('{"event":"upload"}\n', encoding="utf-8")

            snapshot = DashboardStateBuilder(root).snapshot()

        self.assertEqual(snapshot["queue_counts"]["pending"], 1)
        self.assertEqual(snapshot["queue_counts"]["completed"], 1)
        self.assertEqual(snapshot["account_usage"]["a"], 1)
        self.assertEqual(snapshot["account_usage"]["main"], 1)
        self.assertEqual(snapshot["retry_counts"]["job1"], 1)
        self.assertEqual(snapshot["logs"]["upload"][0]["event"], "upload")

    def test_control_store_records_actions_and_pause_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = DashboardControlStore(root)

            retry = store.record("retry", "job1")
            pause = store.record("pause")
            control_file = root / "runtime" / "state" / "dashboard" / "controls.jsonl"
            pause_file = root / "runtime" / "state" / "dashboard" / "queue_control.json"

            lines = control_file.read_text(encoding="utf-8").splitlines()
            pause_state = json.loads(pause_file.read_text(encoding="utf-8"))

        self.assertEqual(retry.action, "retry")
        self.assertEqual(pause.action, "pause")
        self.assertEqual(len(lines), 2)
        self.assertTrue(pause_state["paused"])

    def test_control_store_rejects_unknown_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = DashboardControlStore(temp)

            with self.assertRaisesRegex(ValueError, "unsupported dashboard action"):
                store.record("delete")


if __name__ == "__main__":
    unittest.main()
