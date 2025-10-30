from datetime import timedelta
from unittest.mock import patch
import pytest
import time
from bittensor_wallet import Keypair
from qbittensor.utils.request.JWTManager import JWT
from qbittensor.utils.timestamping import timestamp
from tests.miner.constants import MINER_TEST_DB_NAME
from tests.test_utils import get_mock_keypair

from pkg.database.database_manager import DatabaseManager
from qbittensor.miner.miner_table_initializer import MinerTableInitializer
from qbittensor.miner.runtime.registry import JobRegistry


@pytest.fixture
def registry(monkeypatch) -> JobRegistry:
    db = DatabaseManager(MINER_TEST_DB_NAME)
    MinerTableInitializer(db).create_tables()
    fake_jwt = JWT(
        **{
            "access_token": "test_token",
            "expires_in": 300,
            "expiration_date": timestamp() + timedelta(seconds=300)
        }
    )
    monkeypatch.setattr(
        "qbittensor.utils.request.JWTManager.JWTManager.get_jwt",
        lambda self: fake_jwt
    )
    keypair: Keypair = get_mock_keypair()
    return JobRegistry(db=db, keypair=keypair, poll_interval_s=0.05)

@pytest.fixture(scope="function", autouse=True)
def teardown():
    """Runs once after each test in this session."""
    yield
    print("\nDropping all rows from active_miners table")
    db_manager = DatabaseManager(MINER_TEST_DB_NAME)
    db_manager.query_and_commit("DELETE FROM executions")


def _count_completed(db: DatabaseManager, execution_id: str) -> int:
    query = "SELECT COUNT(*) FROM executions WHERE execution_id=? AND status='Completed'"
    with db.lock:
        rows = db.query_with_values(query, (execution_id,))
    return rows[0][0] if rows else 0


def _get_completed_job_receipt(db: DatabaseManager, execution_id: str):
    query = "SELECT provider, provider_job_id, device_id, status, cost, shots, timestamps_json, metadata_json FROM executions WHERE execution_id=?"
    with db.lock:
        rows = db.query_with_values(query, (execution_id,))
    return rows[0] if rows else None


def test_submit_and_complete_job_writes_db(registry, http_mock):

    execution_id = "123456"
    validator_hotkey = "test_hotkey"
    with patch("qbittensor.miner.runtime.registry.JobRegistry._download_qasm", return_value="mock_qasm"):
        registry.submit(execution_id=execution_id, input_data_url="dataId", validator_hotkey=validator_hotkey)

    deadline = time.time() + 3.0
    while time.time() < deadline:
        from qbittensor.miner.runtime.threads.provider_thread import poll_once
        poll_once(registry)
        if _count_completed(registry.database_manager, execution_id) > 0:
            break
        time.sleep(0.05)

    assert _count_completed(registry.database_manager, execution_id) == 1
    rec = _get_completed_job_receipt(registry.database_manager, execution_id)
    assert rec is not None
    provider, provider_job_id, device_id, status, cost, shots, _, _ = rec
    assert provider == "mock"
    assert provider_job_id is not None and len(provider_job_id) > 0
    assert device_id is not None
    assert status == "Completed"
    assert cost is not None
    assert shots == 1000

    registry.stop()


def test_submit_and_cancel_job_does_not_write_completion(registry, http_mock):

    execution_id = "222333"
    validator_hotkey = "test_hotkey"
    # Mock the call to _download_qasm() to avoid network call delays
    with patch("qbittensor.miner.runtime.registry.JobRegistry._download_qasm", return_value="mock_qasm"):
        registry.submit(execution_id=execution_id, input_data_url="dataId", validator_hotkey=validator_hotkey)

    registry.cancel(execution_id)

    time.sleep(0.3)

    assert _count_completed(registry.database_manager, execution_id) == 0

    registry.stop()


