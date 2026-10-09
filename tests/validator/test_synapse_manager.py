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
import pytest
import bittensor as bt

from qbittensor.database.database_manager import DatabaseManager
from qbittensor.protocol import COLLECT_SYNAPSE_ID
from qbittensor.utils.request.jwt_manager import JWT
from qbittensor.utils.time import timestamp
from qbittensor.validator.compute_request.compute_request import ComputeRequest
from qbittensor.validator.miner_manager.next_miner import BasicMiner
from qbittensor.validator.synapse.synapse_manager import START_OF_TIME, SynapseManager
from tests.test_utils import clean_up_validator_db
from tests.validator.utils import setup_db


req1 = ComputeRequest(execution_id="1", input_data_url="c1", shots=1000, configuration_data={})
req2 = ComputeRequest(execution_id="5", input_data_url="c2", shots=1000, configuration_data={})
req3 = ComputeRequest(execution_id="4", input_data_url="c2", shots=1000, configuration_data={})

TEST_HOTKEY = "test_key"
LAST_CIRCUIT_TIMESTAMP = "2025-08-15 07:30:00"
JOB_SERVER_URL = "http://mockserver"
VALIDATOR_HOTKEY = "test-vali"


def populate_table(db_manager: DatabaseManager) -> None:
    """Setup table rows"""
    query = """
        INSERT OR REPLACE INTO last_circuit
        (miner_hotkey, timestamp)
        VALUES(?, ?)
    """
    values = (TEST_HOTKEY, LAST_CIRCUIT_TIMESTAMP)
    db_manager.query_and_commit_with_values(query, values)

# --------------------------
# Fixtures
# --------------------------


@pytest.fixture
def sm(monkeypatch) -> SynapseManager:
    # Database setup
    db_manager = setup_db()

    # Populate table rows
    populate_table(db_manager)

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

    from unittest.mock import Mock
    from qbittensor.utils.services.job import JobClient
    from qbittensor.utils.services.telemetry import TelemetryService
    job_client = Mock(spec=JobClient)
    tel = Mock(spec=TelemetryService)
    # Create & return
    return SynapseManager(db_manager, telemetry_service=tel, job_client=job_client)


@pytest.fixture
def mock_axon():
    """Create a mock AxonInfo for testing"""
    return bt.AxonInfo(
        version=4,
        ip="127.0.0.1",
        port=8091,
        ip_type=4,
        hotkey="mock_hotkey",
        coldkey="mock_coldkey"
    )


@pytest.fixture
def mock_basic_miner(mock_axon):
    """Create a mock BasicMiner for testing"""
    return BasicMiner(
        uid=2,
        hotkey=TEST_HOTKEY,
        axon=mock_axon
    )


@pytest.fixture(scope="session", autouse=True)
def teardown():
    """Runs once after all tests in this session."""
    yield  # tests run here
    # cleanup logic after all tests
    clean_up_validator_db()


# --------------------------
# Tests for SynapseManager
# --------------------------
def test_get_last_circuit_timestamp(sm):
    last_circuit = sm._get_last_circuit_timestamp(TEST_HOTKEY)
    assert last_circuit is not None
    assert last_circuit == LAST_CIRCUIT_TIMESTAMP


def test_get_last_circuit_timestamp_no_hotkey_data(sm):
    last_circuit = sm._get_last_circuit_timestamp("NO_HOTKEY_DATA")
    assert last_circuit == START_OF_TIME


def test_get_synapse_unexpected_status(sm, mock_basic_miner):
    class MockResponse:
        status_code = 500
    # Patch the instance's request_manager.get directly
    sm.job_client.get_execution_for_miner.return_value = None
    circuit, compute_request = sm.get_synapse(mock_basic_miner)
    assert circuit is None
    assert compute_request is None


def test_get_synapse_success(sm, mock_basic_miner):
    class MockResponse:
        status_code = 200

        def json(self):
            return {"execution_id": "5a78635bc32", "input_data_url": "c2", "shots": 1000, "configuration_data": {}}
    sm.job_client.get_execution_for_miner.return_value = {"execution_id": "5a78635bc32", "input_data_url": "c2", "shots": 1000, "configuration_data": {}}
    circuit, compute_request = sm.get_synapse(mock_basic_miner)
    assert compute_request is not None
    assert circuit is not None
    assert circuit.execution_id == "5a78635bc32"
    assert not circuit.success
    assert not circuit.rate_limited
    assert circuit.last_circuit == LAST_CIRCUIT_TIMESTAMP


def test_get_synapse_no_data(sm, mock_basic_miner):
    sm.job_client.get_execution_for_miner.return_value = {"execution_id": COLLECT_SYNAPSE_ID, "shots": 0}
    circuit, compute_request = sm.get_synapse(mock_basic_miner)
    assert circuit is not None
    assert circuit.execution_id == COLLECT_SYNAPSE_ID
    assert compute_request is not None
    assert compute_request.execution_id == COLLECT_SYNAPSE_ID


def test_get_synapse_unauthorized(sm, mock_basic_miner):
    class MockResponse:
        status_code = 401
    sm.job_client.get_execution_for_miner.return_value = None
    circuit, compute_request = sm.get_synapse(mock_basic_miner)
    assert circuit is None
    assert compute_request is None


def test_get_synapse_invalid_json(sm, mock_basic_miner):
    class MockResponse:
        status_code = 200

        def json(self):
            raise ValueError("Invalid JSON")
    sm.job_client.get_execution_for_miner.return_value = None
    circuit, compute_request = sm.get_synapse(mock_basic_miner)
    assert circuit is None
    assert compute_request is None


def test_get_synapse_none_job(sm, mock_basic_miner):
    # Patch _get_job to return None
    sm._get_job = lambda miner_hotkey: None

    class _Resp:
        status_code = 401
    sm.job_client.get_execution_for_miner.return_value = None
    circuit, compute_request = sm.get_synapse(mock_basic_miner)
    assert circuit is None
    assert compute_request is None


def test_get_last_circuit_timestamp_returns_start_of_time(sm):
    # Should return START_OF_TIME for unknown hotkey
    last_circuit = sm._get_last_circuit_timestamp("unknown_hotkey")
    assert last_circuit == START_OF_TIME
