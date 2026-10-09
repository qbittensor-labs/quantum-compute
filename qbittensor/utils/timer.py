# The MIT License (MIT)
# Copyright © 2026 qBitTensor Labs
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

from datetime import datetime, timedelta
from typing import Callable
import threading

from qbittensor.utils.time import timestamp


class Timer:
    def __init__(
        self,
        timeout: timedelta,
        run: Callable[[], None],
        run_on_start: bool = False,
        run_in_thread: bool = False,
        thread_name: str = "🧵 Timer Thread 🧵",
    ) -> None:
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
            self._timer = timestamp()  # Reset the timer
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
