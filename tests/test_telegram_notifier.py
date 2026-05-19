from __future__ import annotations

import unittest

from integrations.telegram.notifier import TelegramNotifier


class FakeLogger:
    def __init__(self) -> None:
        self.events = []

    def telegram(self, event: str, **fields) -> None:
        self.events.append((event, fields))


class TelegramNotifierTests(unittest.TestCase):
    def test_job_completed_logs_notification_hook(self) -> None:
        logger = FakeLogger()
        notifier = TelegramNotifier(enabled=False, logger=logger)

        notifier.job_completed("job_1", "kenh_1", "upload_id")

        self.assertEqual(logger.events[0][0], "notification_prepared")
        self.assertEqual(logger.events[0][1]["event_name"], "job_completed")
        self.assertEqual(logger.events[0][1]["job_id"], "job_1")


if __name__ == "__main__":
    unittest.main()
