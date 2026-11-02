# The MIT License (MIT)
# Copyright © 2026 qBitTensor Labs
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions
# of the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

"""Monotonic progress clock for the neuron thread.

The outer loop only checks that the background thread is alive. A chain call
that never returns leaves that thread alive and the process up, so neuron-ops
does not restart it. The job sweep and class claim run on that same thread and
must touch this clock so a stall exit does not fire during that work.
"""

import time

# One hour of no progress. Longer than a job sweep or class claim that is
# still moving, shorter than an overnight wedged chain read.
NEURON_STALL_EXIT_S = 60 * 60

_progress_at: float | None = None


def touch_neuron_progress() -> None:
    """Record that the neuron thread is still doing work."""
    global _progress_at
    _progress_at = time.monotonic()


def seconds_since_neuron_progress() -> float | None:
    """Seconds since the last touch, or None if nothing has been recorded."""
    if _progress_at is None:
        return None
    return time.monotonic() - _progress_at


def neuron_progress_is_stale(limit_s: float = NEURON_STALL_EXIT_S) -> bool:
    stale = seconds_since_neuron_progress()
    return stale is not None and stale > limit_s
