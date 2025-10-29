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
    registry.submit(execution_id, input_data_url="http://qasm", validator_hotkey="vk", shots=10)

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
    registry.submit(execution_id, input_data_url="http://qasm", validator_hotkey="vk", shots=10)

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


