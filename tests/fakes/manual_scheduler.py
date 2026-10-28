"""An APScheduler scheduler with no background thread: tests call tick() under freezegun.

It uses the real SQLAlchemy job store and triggers, so persistence and timing are real.
"""

from typing import Any

from apscheduler.executors.debug import DebugExecutor
from apscheduler.schedulers.base import BaseScheduler

from escalate.scheduler.jobs import scheduler_config


class ManualScheduler(BaseScheduler):
    def __init__(self, url: str, **kw: Any) -> None:
        cfg = scheduler_config(url)
        cfg["executors"] = {"default": DebugExecutor()}
        super().__init__(**cfg, **kw)

    def shutdown(self, wait: bool = True) -> None:
        super().shutdown(wait)

    def wakeup(self) -> None:
        pass

    def tick(self) -> None:
        self._process_jobs()
