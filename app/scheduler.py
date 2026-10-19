"""백그라운드 스레드에서 주기적으로 monitor.run_cycle() 실행."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from . import config, db, monitor

log = logging.getLogger("job_watch")


def _interval_seconds() -> float:
    try:
        minutes = float(db.get_settings().get("interval_minutes", "60"))
    except ValueError:
        minutes = 60
    return max(10.0, minutes) * 60  # 사이트 부담을 줄이려고 최소 10분


def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts, config.KST).strftime("%Y-%m-%d %H:%M:%S")


class Scheduler:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._stopped = False
        self._run_requested = False
        self._last_end = time.time()
        self.next_run = 0.0

    def start(self, first_delay: float = 5.0) -> None:
        self.next_run = time.time() + first_delay
        threading.Thread(target=self._loop, name="scheduler", daemon=True).start()

    def stop(self) -> None:
        self._stopped = True
        self._event.set()

    def trigger(self) -> bool:
        """지금 바로 수집. 이미 실행 중이면 False."""
        if monitor.state["running"]:
            return False
        self._run_requested = True
        self._event.set()
        return True

    def reschedule(self) -> None:
        """수집 주기 설정이 바뀌었을 때 다음 실행 시각을 다시 계산."""
        self.next_run = self._last_end + _interval_seconds()
        self._event.set()

    def _loop(self) -> None:
        while not self._stopped:
            monitor.state["next_run"] = _fmt(self.next_run)
            # PC 절전 복귀 등에 대비해 최대 60초씩 끊어서 기다린다
            self._event.wait(timeout=min(60.0, max(0.0, self.next_run - time.time())))
            self._event.clear()
            if self._stopped:
                break
            if not self._run_requested and time.time() < self.next_run:
                continue
            manual, self._run_requested = self._run_requested, False
            try:
                monitor.run_cycle("manual" if manual else "schedule")
            except Exception:
                log.exception("수집 실패")
            self._last_end = time.time()
            self.next_run = self._last_end + _interval_seconds()


scheduler = Scheduler()
