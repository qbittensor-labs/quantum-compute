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

from qbittensor.miner.providers.base import JobHandle
from qbittensor.miner.runtime import repository as repo
from qbittensor.validator.utils.execution_status import ExecutionStatus


class _EmptyHandle:
    provider_job_id = None
    device_id = None


def _status(dbm, execution_id):
    with dbm.lock:
        rows = dbm.query_with_values(
            "SELECT status, errorMessage FROM executions WHERE execution_id = ?",
            (execution_id,),
        )
    return rows[0] if rows else None


def test_restore_reloads_queued_provider_job(registry):
    repo.insert_pending(
        registry,
        execution_id="queued-1",
        validator_hotkey="vhk",
        handle=_EmptyHandle(),
        shots=4,
    )
    repo.update_to_queued(
        registry,
        execution_id="queued-1",
        handle=JobHandle(provider_job_id="prov-9", device_id="dev-9"),
    )
    restored = registry.restore_open_executions()
    assert restored == 1
    tracked = registry._jobs["queued-1"]
    assert tracked.handle.provider_job_id == "prov-9"
    assert tracked.handle.device_id == "dev-9"
    assert tracked.validator_hotkey == "vhk"
    assert registry._provider_thread is None


def test_restore_resubmits_pending_with_circuit_url(registry, monkeypatch):
    calls = []

    def fake_submit(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(registry, "submit", fake_submit)
    repo.insert_pending(
        registry,
        execution_id="pending-url",
        validator_hotkey="vhk",
        handle=_EmptyHandle(),
        shots=7,
        input_data_url="http://circuit",
        configuration_data={"shots": 7},
        backend_class_id="quantumrings:qasm3",
    )
    restored = registry.restore_open_executions()
    registry.join_submits(2)
    assert restored == 1
    assert calls[0]["execution_id"] == "pending-url"
    assert calls[0]["input_data_url"] == "http://circuit"
    assert calls[0]["validator_hotkey"] == "vhk"
    assert calls[0]["shots"] == 7
    assert calls[0]["configuration_data"] == {"shots": 7}
    assert calls[0]["backend_class_id"] == "quantumrings:qasm3"
    assert registry._provider_thread is None


def test_restore_fails_open_row_with_nothing_to_resume(registry):
    repo.insert_pending(
        registry,
        execution_id="pending-empty",
        validator_hotkey="vhk",
        handle=_EmptyHandle(),
        shots=1,
    )
    restored = registry.restore_open_executions()
    assert restored == 0
    assert "pending-empty" not in registry._jobs
    status, message = _status(registry.database_manager, "pending-empty")
    assert status == ExecutionStatus.FAILED
    assert message == "Lost before provider submit"
