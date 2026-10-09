# The MIT License (MIT)
# Copyright © 2026 qBitTensor Labs

from __future__ import annotations

import signal
from collections.abc import Callable


def install_shutdown(neuron, *on_signal: Callable[[], None]) -> None:
    """Ask the neuron to leave its loop. The handler only sets flags."""

    def handler(signum, _frame):
        neuron.should_exit = True
        for callback in on_signal:
            try:
                callback()
            except Exception:
                pass

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)
