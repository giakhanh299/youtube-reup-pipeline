from __future__ import annotations

from typing import Any, Callable

from logs.structured_logger import NullLogger
from utils.retry import RetryStrategy, retry_selenium


class BrowserManager:
    """Optional Selenium session manager with retry and cleanup hooks."""

    def __init__(
        self,
        driver_factory: Callable[[], Any] | None = None,
        retry_strategy: RetryStrategy | None = None,
        logger: Any = None,
    ):
        self.driver_factory = driver_factory
        self.retry_strategy = retry_strategy
        self.logger = logger or NullLogger()
        self.driver: Any = None

    def start(self) -> Any:
        if self.driver:
            return self.driver
        if not self.driver_factory:
            raise RuntimeError("Selenium driver_factory is not configured")
        self.driver = retry_selenium(self.driver_factory, self.retry_strategy, "selenium_start_browser")
        self.logger.selenium("browser_started")
        return self.driver

    def run(self, operation: Callable[[Any], Any], operation_name: str = "selenium_operation") -> Any:
        def _call() -> Any:
            driver = self.start()
            return operation(driver)

        return retry_selenium(_call, self.retry_strategy, operation_name)

    def recover(self) -> Any:
        self.cleanup()
        self.logger.selenium("browser_recovering")
        return self.start()

    def cleanup(self) -> None:
        if not self.driver:
            return
        try:
            quit_method = getattr(self.driver, "quit", None)
            if callable(quit_method):
                quit_method()
            self.logger.selenium("browser_closed")
        finally:
            self.driver = None

    def __enter__(self) -> "BrowserManager":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()
