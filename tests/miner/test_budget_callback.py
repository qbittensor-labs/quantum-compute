import time
import pytest

from pkg.database.database_manager import DatabaseManager
from qbittensor.miner.miner_table_initializer import MinerTableInitializer
from qbittensor.miner.runtime.registry import JobRegistry
from qbittensor.miner.runtime.threads.provider_thread import poll_once
from tests.test_utils import get_mock_keypair


@pytest.fixture
def tmp_db():
    db_name = "test_budget_cb"
    db = DatabaseManager(db_name)
    MinerTableInitializer(db).create_tables()
    return db


def _count_completed(db: DatabaseManager, execution_id: str) -> int:
    query = "SELECT COUNT(*) FROM executions WHERE execution_id=? AND status='Completed'"
    with db.lock:
        rows = db.query_with_values(query, (execution_id,))
    return rows[0][0] if rows else 0


def test_on_job_completed_completes_and_persists(tmp_db, monkeypatch, http_mock):
    keypair = get_mock_keypair()
    jr = JobRegistry(tmp_db, keypair, poll_interval_s=0.02)

    execution_id = "91011"
    monkeypatch.setattr(jr, "_download_qasm", lambda url: "OPENQASM 2.0; // mock")
    jr.submit(execution_id=execution_id, input_data_url="http://qasm", validator_hotkey="hk", shots=10)
    
    jr.start()
    
    deadline = time.time() + 3.0
    while time.time() < deadline and _count_completed(tmp_db, execution_id) == 0:
        poll_once(jr)
        time.sleep(0.05)
    
    jr.stop()

    assert _count_completed(tmp_db, execution_id) == 1


