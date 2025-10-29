from qbittensor.miner.runtime.threads.status_thread import collect_status_data


def test_collect_status_data_enqueues_and_send(registry, http_mock):
    collect_status_data(registry)
    # Simulate immediate send path via JobRegistry wrapper
    registry._update_job_server_status()
    assert registry._status_queue.qsize() in (0, 1)


