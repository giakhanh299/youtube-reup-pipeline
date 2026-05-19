from __future__ import annotations

import unittest

from services.scheduler_service import SchedulerDaemon, SchedulerTask


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


if __name__ == "__main__":
    unittest.main()
