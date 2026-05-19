from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Any, Callable

from logs.structured_logger import NullLogger


@dataclass
class SchedulerTask:
    name: str
    interval_seconds: float
    action: Callable[[], Any]
    retry_interval_seconds: float | None = None
    next_run: float = 0.0
    run_count: int = 0
    error_count: int = 0
    last_result_count: int = 0
    last_error: str = ""


@dataclass(frozen=True)
class SchedulerSnapshot:
    cycles: int
    task_stats: dict[str, dict] = field(default_factory=dict)


class SchedulerDaemon:
    """Simple cooperative scheduler for render/upload cycles."""

    def __init__(
        self,
        tasks: list[SchedulerTask],
        heartbeat_interval_seconds: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
        logger: Any = None,
        stop_event: threading.Event | None = None,
    ):
        self.tasks = tasks
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.sleep = sleep
        self.clock = clock
        self.logger = logger or NullLogger()
        self.stop_event = stop_event or threading.Event()
        self.cycles = 0
        self._next_heartbeat = 0.0

    def stop(self) -> None:
        self.stop_event.set()

    def _result_count(self, result: Any) -> int:
        if result is None:
            return 0
        if isinstance(result, (list, tuple, set, dict)):
            return len(result)
        return 1

    def _run_task(self, task: SchedulerTask, now: float) -> None:
        if task.next_run and now < task.next_run:
            return
        try:
            self.logger.worker("scheduler_task_started", task=task.name)
            result = task.action()
            task.run_count += 1
            task.last_result_count = self._result_count(result)
            task.last_error = ""
            task.next_run = now + max(task.interval_seconds, 0.0)
            self.logger.worker(
                "scheduler_task_finished",
                task=task.name,
                run_count=task.run_count,
                result_count=task.last_result_count,
            )
        except Exception as exc:
            task.error_count += 1
            task.last_error = str(exc)
            retry_interval = task.retry_interval_seconds
            if retry_interval is None:
                retry_interval = task.interval_seconds
            task.next_run = now + max(retry_interval, 0.0)
            self.logger.error(
                "scheduler_task_failed",
                task=task.name,
                error=str(exc),
                error_count=task.error_count,
            )

    def _heartbeat(self, now: float) -> None:
        if self._next_heartbeat and now < self._next_heartbeat:
            return
        self.logger.worker(
            "scheduler_heartbeat",
            cycles=self.cycles,
            task_stats=self.snapshot().task_stats,
        )
        self._next_heartbeat = now + max(self.heartbeat_interval_seconds, 0.0)

    def snapshot(self) -> SchedulerSnapshot:
        return SchedulerSnapshot(
            cycles=self.cycles,
            task_stats={
                task.name: {
                    "run_count": task.run_count,
                    "error_count": task.error_count,
                    "last_result_count": task.last_result_count,
                    "last_error": task.last_error,
                    "next_run": task.next_run,
                }
                for task in self.tasks
            },
        )

    def run(self, max_cycles: int | None = None) -> SchedulerSnapshot:
        self.logger.worker("scheduler_started", task_count=len(self.tasks))
        while not self.stop_event.is_set():
            now = self.clock()
            self._heartbeat(now)
            for task in self.tasks:
                self._run_task(task, now)
            self.cycles += 1
            if max_cycles is not None and self.cycles >= max_cycles:
                break
            self.sleep(1.0)
        self.logger.worker("scheduler_stopped", cycles=self.cycles)
        return self.snapshot()
