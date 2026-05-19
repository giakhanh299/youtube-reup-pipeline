from __future__ import annotations

import unittest

from integrations.selenium.browser_manager import BrowserManager
from utils.retry import RetryStrategy


class FakeDriver:
    def __init__(self) -> None:
        self.closed = False

    def quit(self) -> None:
        self.closed = True


class BrowserManagerTests(unittest.TestCase):
    def test_start_reuses_driver_and_cleanup_quits(self) -> None:
        created = []

        def factory() -> FakeDriver:
            driver = FakeDriver()
            created.append(driver)
            return driver

        manager = BrowserManager(factory, RetryStrategy(max_attempts=1, sleep=lambda delay: None))

        first = manager.start()
        second = manager.start()
        manager.cleanup()

        self.assertIs(first, second)
        self.assertEqual(len(created), 1)
        self.assertTrue(first.closed)
        self.assertIsNone(manager.driver)

    def test_missing_factory_raises_clear_error(self) -> None:
        manager = BrowserManager()

        with self.assertRaisesRegex(RuntimeError, "driver_factory"):
            manager.start()


if __name__ == "__main__":
    unittest.main()
