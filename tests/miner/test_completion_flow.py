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

from qbittensor.miner.runtime.flows import completion_flow as cf


def test_valid_counts_accepts_binary_keys_positive_ints():
    assert cf._valid_counts({"0": 1, "1": 2})
    assert cf._valid_counts({"00": 1, "11": 0, "01": 3})
    assert not cf._valid_counts({})
    assert not cf._valid_counts({"2": 1})
    assert not cf._valid_counts({"01": -1})


def test_persist_completion_happy_path(registry, http_mock, monkeypatch):
    # Arrange: submit a job -> progress to COMPLETED -> persist
    execution_id = "exec-1"
    registry.submit(
        execution_id,
        input_data_url="http://qasm",
        validator_hotkey="vk",
        shots=10,
        backend_class_id="test-class",
    )

    # Force provider job to completed quickly
    for _ in range(200):
        from qbittensor.miner.runtime.threads.provider_thread import poll_once
        poll_once(registry)
        if any(j.last_status == "COMPLETED" for j in registry._jobs.values()):
            break

    # Act: invoke persist_completion directly on tracked job
    tracked = list(registry._jobs.values())[0]
    # Make receipt contain valid measurementCounts

    class GoodReceipt:
        provider = "mock"
        provider_job_id = tracked.handle.provider_job_id if hasattr(tracked.handle, "provider_job_id") else "job_x"
        status = "COMPLETED"
        device_id = "mock_qpu_1"
        results = {"measurementCounts": {"00": 1, "11": 1}}

    monkeypatch.setattr(registry.adapter, "get_job_receipt", lambda h: GoodReceipt)
    finalized = cf.persist_completion(registry, tracked)

    # Assert
    assert finalized is True


def test_persist_completion_invalid_counts_fails(registry, http_mock, monkeypatch):
    # Arrange
    execution_id = "exec-2"
    registry.submit(
        execution_id,
        input_data_url="http://qasm",
        validator_hotkey="vk",
        shots=10,
        backend_class_id="test-class",
    )

    # Make receipt return invalid counts by monkeypatching adapter.get_job_receipt
    class BadReceipt:
        provider = "mock"
        provider_job_id = "job_bad"
        status = "COMPLETED"
        device_id = "mock_qpu_1"
        results = {"measurementCounts": {"2": 1}}  # invalid key

    orig = registry.adapter.get_job_receipt
    monkeypatch.setattr(registry.adapter, "get_job_receipt", lambda h: BadReceipt)

    tracked = list(registry._jobs.values())[0]
    finalized = cf.persist_completion(registry, tracked)
    assert finalized is False
    monkeypatch.setattr(registry.adapter, "get_job_receipt", orig)
