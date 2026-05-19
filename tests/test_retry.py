from __future__ import annotations

import unittest

from utils.retry import RetryStrategy


class FakeLogger:
    def __init__(self) -> None:
        self.retry_events = []
        self.error_events = []

    def retry(self, event: str, **fields) -> None:
        self.retry_events.append((event, fields))

    def error(self, event: str, **fields) -> None:
        self.error_events.append((event, fields))


class RetryStrategyTests(unittest.TestCase):
    def test_retry_succeeds_after_transient_failure(self) -> None:
        calls = {"count": 0}
        delays = []
        logger = FakeLogger()

        def operation() -> str:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("temporary")
            return "ok"

        strategy = RetryStrategy(max_attempts=3, base_delay=0.5, sleep=delays.append, logger=logger)

        result = strategy.run(operation, "test_operation", "test")

        self.assertEqual(result, "ok")
        self.assertEqual(calls["count"], 2)
        self.assertEqual(delays, [0.5])
        self.assertEqual(len(logger.retry_events), 1)
        self.assertEqual(logger.error_events, [])

    def test_retry_raises_after_max_attempts(self) -> None:
        delays = []
        logger = FakeLogger()
        strategy = RetryStrategy(max_attempts=2, base_delay=0.1, sleep=delays.append, logger=logger)

        with self.assertRaises(RuntimeError):
            strategy.run(lambda: (_ for _ in ()).throw(RuntimeError("fail")), "always_fails", "test")

        self.assertEqual(delays, [0.1])
        self.assertEqual(len(logger.retry_events), 1)
        self.assertEqual(len(logger.error_events), 1)


if __name__ == "__main__":
    unittest.main()
