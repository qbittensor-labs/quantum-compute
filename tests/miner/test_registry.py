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

from datetime import timedelta
from unittest.mock import patch
import pytest
import time
# Keypair type comes via get_mock_keypair() which returns bt.Keypair
# (no direct bittensor_wallet import needed)
from qbittensor.utils.request.jwt_manager import JWT
from qbittensor.utils.time import timestamp
from tests.miner.constants import MINER_TEST_DB_NAME
from tests.test_utils import get_mock_keypair

from qbittensor.database.database_manager import DatabaseManager
from qbittensor.constants import JOB_POLL_INTERVAL_S
from qbittensor.miner.runtime.registry import JobRegistry


def test_default_job_poll_interval_is_30s():
    import inspect

    default = inspect.signature(JobRegistry.__init__).parameters["poll_interval_s"].default
    assert JOB_POLL_INTERVAL_S == 30.0
    assert default == 30.0


@pytest.fixture
def registry(monkeypatch) -> JobRegistry:
    db = DatabaseManager(MINER_TEST_DB_NAME)
    # migrations applied on construction
    fake_jwt = JWT(
        **{
            "access_token": "test_token",
            "expires_in": 300,
            "expiration_date": timestamp() + timedelta(seconds=300)
        }
    )
    monkeypatch.setattr(
        "qbittensor.utils.request.jwt_manager.JWTManager.get_jwt",
        lambda self: fake_jwt
    )
    keypair = get_mock_keypair()
    from unittest.mock import Mock
    from qbittensor.utils.services.job import JobClient
    jc = Mock(spec=JobClient)
    jc.request_upload_slot.return_value = {"upload_url": "http://ex", "id": "u1"}
    return JobRegistry(db=db, keypair=keypair, poll_interval_s=0.05, job_client=jc)


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
        registry.submit(
            execution_id=execution_id,
            input_data_url="dataId",
            validator_hotkey=validator_hotkey,
            backend_class_id="test-class",
        )

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
    assert shots is None

    registry.stop()


def test_submit_and_cancel_job_does_not_write_completion(registry, http_mock):

    execution_id = "222333"
    validator_hotkey = "test_hotkey"
    # Mock the call to _download_qasm() to avoid network call delays
    with patch("qbittensor.miner.runtime.registry.JobRegistry._download_qasm", return_value="mock_qasm"):
        registry.submit(
            execution_id=execution_id,
            input_data_url="dataId",
            validator_hotkey=validator_hotkey,
            backend_class_id="test-class",
        )

    registry.cancel(execution_id)

    time.sleep(0.3)

    assert _count_completed(registry.database_manager, execution_id) == 0

    registry.stop()


def test_submit_without_backend_class_does_not_call_provider(registry, http_mock):
    called = []
    registry.adapter.submit = lambda *args, **kwargs: called.append(kwargs)
    with patch(
        "qbittensor.miner.runtime.registry.JobRegistry._download_qasm",
        return_value="mock_qasm",
    ):
        registry.submit(
            execution_id="no-class",
            input_data_url="dataId",
            validator_hotkey="test_hotkey",
        )
    assert called == []
    with registry.database_manager.lock:
        rows = registry.database_manager.query_with_values(
            "SELECT status, device_id, errorMessage FROM executions WHERE execution_id=?",
            ("no-class",),
        )
    assert rows[0][0] == "Failed"
    assert rows[0][1] is None
    assert rows[0][2] == "Claim has no backend class"
    registry.stop()
