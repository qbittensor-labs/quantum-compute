import json

from qbittensor.miner.runtime import repository as repo
from qbittensor.validator.utils.execution_status import ExecutionStatus


class DummyHandle:
    def __init__(self):
        self.provider_job_id = "prov-1"
        self.device_id = "mock_qpu_1"


class DummyRegistry:
    def __init__(self, dbm):
        self.database_manager = dbm
        self._default_device = type("D", (), {"provider": "mock"})()


def _read_exec(dbm, execution_id):
    with dbm.lock:
        rows = dbm.query_with_values(
            "SELECT execution_id, validator_hotkey, provider, provider_job_id, device_id, status, shots, metadata_json, errorMessage FROM executions WHERE execution_id = ?",
            (execution_id,),
        )
    return rows[0] if rows else None


def test_insert_pending_and_update_status(db_manager):
    r = DummyRegistry(db_manager)
    repo.insert_pending(r, execution_id="e1", validator_hotkey="vhk", handle=DummyHandle(), shots=123)
    row = _read_exec(db_manager, "e1")
    assert row is not None
    assert row[0] == "e1"
    assert row[1] == "vhk"
    assert row[2] == "mock"
    assert row[3] == "prov-1"
    assert row[4] == "mock_qpu_1"
    # Initial insert should be Pending per new lifecycle
    assert row[5] == ExecutionStatus.PENDING
    assert row[6] == 123

    repo.update_status(r, execution_id="e1", status=ExecutionStatus.RUNNING)
    row2 = _read_exec(db_manager, "e1")
    assert row2[5] == ExecutionStatus.RUNNING


def test_persist_failed(db_manager):
    r = DummyRegistry(db_manager)
    repo.persist_failed(
        r,
        execution_id="e2",
        validator_hotkey="vhk",
        provider="mock",
        provider_job_id="prov-2",
        device_id="mock_qpu_1",
        error_message="boom",
        metadata={"a": 1},
    )
    row = _read_exec(db_manager, "e2")
    assert row[5] == ExecutionStatus.FAILED
    assert json.loads(row[7]) == {"a": 1}
    assert row[8] == "boom"


def test_persist_completed(db_manager):
    class T:
        execution_id = "e3"
        validator_hotkey = "vhk"

    class R:
        provider = "mock"
        provider_job_id = "prov-3"
        device_id = "mock_qpu_1"
        cost = 0.01
        shots = 100
        timestamps = {"a": 1}
        metadata = {"m": True}

    r = DummyRegistry(db_manager)
    repo.persist_completed(r, tracked=T(), receipt=R(), upload_data_id="rid")
    row = _read_exec(db_manager, "e3")
    assert row[5] == ExecutionStatus.COMPLETED
    assert json.loads(row[7]) == {"m": True}


