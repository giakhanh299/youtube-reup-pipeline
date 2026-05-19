from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable, TypeVar

from logs.structured_logger import NullLogger

T = TypeVar("T")


@dataclass
class RetryStrategy:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    sleep: Callable[[float], None] = time.sleep
    logger: Any = None

    def run(self, operation: Callable[[], T], operation_name: str, category: str = "external") -> T:
        logger = self.logger or NullLogger()
        attempt = 1
        while True:
            try:
                return operation()
            except Exception as exc:
                if attempt >= self.max_attempts:
                    logger.error(
                        "retry_exhausted",
                        operation=operation_name,
                        category=category,
                        attempt=attempt,
                        error=str(exc),
                    )
                    raise

                delay = min(self.base_delay * (self.backoff_factor ** (attempt - 1)), self.max_delay)
                logger.retry(
                    "retry_scheduled",
                    operation=operation_name,
                    category=category,
                    attempt=attempt,
                    delay=delay,
                    error=str(exc),
                )
                self.sleep(delay)
                attempt += 1


def retry_google_api(operation: Callable[[], T], strategy: RetryStrategy | None = None, operation_name: str = "google_api") -> T:
    return (strategy or RetryStrategy()).run(operation, operation_name, "google_api")


def retry_selenium(operation: Callable[[], T], strategy: RetryStrategy | None = None, operation_name: str = "selenium") -> T:
    return (strategy or RetryStrategy()).run(operation, operation_name, "selenium")


def retry_ffmpeg(operation: Callable[[], T], strategy: RetryStrategy | None = None, operation_name: str = "ffmpeg") -> T:
    return (strategy or RetryStrategy()).run(operation, operation_name, "ffmpeg")


def retry_http(operation: Callable[[], T], strategy: RetryStrategy | None = None, operation_name: str = "http") -> T:
    return (strategy or RetryStrategy()).run(operation, operation_name, "http")
