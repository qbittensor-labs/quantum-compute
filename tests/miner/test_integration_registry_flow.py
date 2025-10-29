import time

from qbittensor.miner.runtime.threads.provider_thread import poll_once


def test_integration_registry_flow_end_to_end(registry, http_mock):
    # Submit -> poll -> complete -> persisted -> removed from tracking
    exec_id = "INT-1"
    registry.submit(exec_id, input_data_url="http://qasm", validator_hotkey="vhk")
    # Progress provider state until completed and clean-up
    for _ in range(300):
        poll_once(registry)
        with registry._lock:
            if exec_id not in registry._jobs:
                break
        time.sleep(0.01)
    assert not registry.is_tracking(exec_id)
    # Row is completed in DB
    rows = registry.db.query_with_values(
        "SELECT status, upload_data_id FROM executions WHERE execution_id = ?",
        (exec_id,),
    )
    assert rows and rows[0][0] == "Completed"
    assert rows[0][1] is not None


