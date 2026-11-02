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


def _track_cancel_job(registry, execution_id: str, requested: bool):
    from qbittensor.miner.providers.base import JobHandle
    from qbittensor.miner.runtime.types import _TrackedJob

    handle = JobHandle(provider_job_id=f"job-{execution_id}", device_id="class")
    tracked = _TrackedJob(execution_id, "vhk", handle)
    if requested:
        tracked.cancel_requested = True
    with registry._lock:
        registry._jobs[execution_id] = tracked


def test_provider_thread_requested_cancel_message(registry, http_mock, monkeypatch):
    from qbittensor.miner.providers.base import BaseExecutionStatus

    _track_cancel_job(registry, "C1", True)
    monkeypatch.setattr(
        registry.adapter,
        "poll",
        lambda handle: BaseExecutionStatus(status="CANCELLED", message=None),
    )
    persisted = {}

    def _persist(_registry, **kwargs):
        persisted.update(kwargs)

    monkeypatch.setattr(pt, "persist_failed", _persist)
    pt.poll_once(registry)
    assert persisted["error_message"] == "User canceled"


def test_provider_thread_unsolicited_cancel_is_not_a_user_cancel(
    registry, http_mock, monkeypatch
):
    from qbittensor.miner.providers.base import BaseExecutionStatus

    _track_cancel_job(registry, "C2", False)
    monkeypatch.setattr(
        registry.adapter,
        "poll",
        lambda handle: BaseExecutionStatus(status="CANCELLED", message=None),
    )
    persisted = {}

    def _persist(_registry, **kwargs):
        persisted.update(kwargs)

    monkeypatch.setattr(pt, "persist_failed", _persist)
    pt.poll_once(registry)
    assert persisted["error_message"] == "Cancelled by request"


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
