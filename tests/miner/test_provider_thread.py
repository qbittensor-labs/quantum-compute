from qbittensor.miner.runtime.threads import provider_thread as pt


def test_provider_thread_poll_once_handles_unknown_job(registry, http_mock, monkeypatch):
    # Submit job then remove it from adapter to simulate unknown
    exec_id = "B1"
    registry.submit(exec_id, input_data_url="http://qasm", validator_hotkey="vhk")
    with registry._lock:
        tr = registry._jobs[exec_id]
    # Monkeypatch adapter.poll to raise an exception to exercise error path
    def boom(handle):
        raise RuntimeError("poll-failure")
    monkeypatch.setattr(registry.adapter, "poll", boom)
    pt.poll_once(registry)
    # Still tracked, but last_status unchanged
    with registry._lock:
        assert exec_id in registry._jobs


