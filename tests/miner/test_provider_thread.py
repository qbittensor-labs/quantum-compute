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

from qbittensor.miner.runtime.threads import provider_thread as pt


def test_provider_thread_poll_once_handles_unknown_job(registry, http_mock, monkeypatch):
    # Submit job then remove it from adapter to simulate unknown
    exec_id = "B1"
    registry.submit(
        exec_id,
        input_data_url="http://qasm",
        validator_hotkey="vhk",
        backend_class_id="test-class",
    )
    # Monkeypatch adapter.poll to raise an exception to exercise error path

    def boom(handle):
        raise RuntimeError("poll-failure")
    monkeypatch.setattr(registry.adapter, "poll", boom)
    pt.poll_once(registry)
    # Still tracked, but last_status unchanged
    with registry._lock:
        assert exec_id in registry._jobs
