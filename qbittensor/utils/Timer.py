from datetime import datetime, timedelta
from typing import Callable
import threading

from qbittensor.utils.timestamping import timestamp

class Timer:
    def __init__(self, timeout: timedelta, run: Callable[[], None], run_on_start: bool = False, run_in_thread: bool = False, thread_name: str = "🧵 Timer Thread 🧵") -> None:
        super().__init__()
        self._run = run
        self._timeout: timedelta = timeout
        self._run_in_thread = run_in_thread
        self._thread_name = thread_name

        # Check if we want to run the task on start
        if run_on_start:
            self._timer: datetime = timestamp() - timeout
        else:
            self._timer: datetime = timestamp()

    def check_timer(self) -> None:
        """Check the timer. If it's time, reset timer and call _start()"""
        if self._should_start():
            self._timer = timestamp() # Reset the timer
            self._start()

    def _start(self) -> None:
        """Start the execution of the task"""
        if self._run_in_thread:
            threading.Thread(target=self._run, name=self._thread_name).start()
        else:
            self._run()

    def _should_start(self) -> bool:
        """Return wether or not the task should start"""
        now: datetime = timestamp()
        time_diff: timedelta = now - self._timer
        return time_diff >= self._timeout
