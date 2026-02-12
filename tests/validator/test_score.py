from datetime import timedelta
import pytest
import bittensor as bt

from pkg.database.database_manager import DatabaseManager
from qbittensor.protocol import CircuitSynapse, ExecutionData
from qbittensor.utils.request.JWTManager import JWT
from qbittensor.utils.timestamping import timestamp
from qbittensor.validator.compute_request.ComputeRequest import ComputeRequest
from qbittensor.validator.miner_manager.NextMiner import BasicMiner
from qbittensor.validator.reward.score import Scorer
from qbittensor.utils.request.RequestManager import RequestManager
from qbittensor.validator.utils.execution_status import ExecutionStatus
from tests.miner.constants import VALIDATOR_TEST_DB_NAME
from tests.test_utils import clean_up_validator_db, get_mock_keypair, get_mock_metagraph
from unittest.mock import patch


#---------
# Fixtures
#---------

@pytest.fixture(scope="module", autouse=True)
def teardown():
    """Runs once after each test."""
    yield  # tests run here
    # cleanup logic after all tests
    clean_up_validator_db()

@pytest.fixture
def scorer(monkeypatch):
    database_manager = DatabaseManager(VALIDATOR_TEST_DB_NAME)
    keypair: bt.Keypair = get_mock_keypair()

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
    request_manager = RequestManager(keypair)
    metagraph: bt.Metagraph = get_mock_metagraph(5)
    return Scorer(database_manager, metagraph, request_manager)

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
def synapse():
    return CircuitSynapse(
        execution_id="job123",
        input_data_url="sample_circuit_data",
        shots=1024,
        configuration_data={"sample_configuration_key": "sample_configuration_value"},
        success=True,
        last_circuit="2023-10-01T12:00:00Z",
        rate_limited=False,
        finished_executions=[
            ExecutionData(
                execution_id="job123",
                shots=1024,
                upload_data_id="dataid123",
                status=ExecutionStatus.COMPLETED,
                execution_data={"provider_job_id": "provider_job_123"}
            ),
        ]
    )

@pytest.fixture
def synapse_with_failed_execution():
    return CircuitSynapse(
        execution_id="job123",
        input_data_url="sample_circuit_data",
        shots=1024,
        configuration_data={"sample_configuration_key": "sample_configuration_value"},
        success=True,
        last_circuit="2023-10-01T12:00:00Z",
        rate_limited=False,
        finished_executions=[
            ExecutionData(
                execution_id="job123",
                shots=1024,
                upload_data_id="dataid123",
                status=ExecutionStatus.COMPLETED,
                execution_data={"provider_job_id": "provider_job_123"}
            ),
            ExecutionData(
                execution_id="job234",
                shots=1024,
                upload_data_id="dataid234",
                status=ExecutionStatus.COMPLETED,
                execution_data={"provider_job_id": "provider_job_234"}
            ),
            ExecutionData(
                execution_id="job345",
                shots=1024,
                upload_data_id="dataid345",
                status=ExecutionStatus.FAILED,
                errorMessage="Some error occurred",
                execution_data={"provider_job_id": "provider_job_345"}
            ),
        ]
    )

@pytest.fixture
def compute_request() -> ComputeRequest:
    return ComputeRequest(
            execution_id="job123",
            input_data_url="sample_circuit_data",
            shots=1024,
            configuration_data={"sample_configuration_key": "sample_configuration_value"}
        )


#------
# Tests
#------

def test_synapse_success_false(scorer: Scorer, synapse: CircuitSynapse, compute_request: ComputeRequest, mock_axon):
    """Test that we call the function to reject the job when success is False"""
    synapse.success = False
    with patch.object(scorer, "_patch_job_rejected") as mock_patch_job_rejected:
        scorer.process_miner_responses([synapse], BasicMiner(hotkey="miner_hotkey_1", uid=2, axon=mock_axon), compute_request)
        mock_patch_job_rejected.assert_called_once_with(synapse.execution_id, "Miner did not respond")

def test_synapse_rate_limited(scorer: Scorer, synapse: CircuitSynapse, compute_request: ComputeRequest, mock_axon):
    """Test that we call the function to reject the job when rate_limited is True"""
    synapse.rate_limited = True
    with patch.object(scorer, "_patch_job_rejected") as mock_patch_job_rejected:
        scorer.process_miner_responses([synapse], BasicMiner(hotkey="miner_hotkey_1", uid=2, axon=mock_axon), compute_request)
        mock_patch_job_rejected.assert_called_once_with(synapse.execution_id, "Miner is rate limiting")

def test_synapse_with_failed_execution(scorer: Scorer, synapse_with_failed_execution: CircuitSynapse, compute_request: ComputeRequest, mock_axon):
    """Test that we call the function to reject the job for the failed execution and complete for the successful ones"""
    with patch.object(scorer, "_patch_job_rejected") as mock_patch_job_rejected, \
        patch.object(scorer, "_patch_job_complete") as mock_patch_job_complete:
        scorer.process_miner_responses([synapse_with_failed_execution], BasicMiner(hotkey="miner_hotkey_1", uid=2, axon=mock_axon), compute_request)
        
        mock_patch_job_rejected.assert_called_once_with(
            synapse_with_failed_execution.finished_executions[2].execution_id,
            "Some error occurred",
            synapse_with_failed_execution.finished_executions[2].execution_data
        )
        assert mock_patch_job_complete.call_count == 2
        mock_patch_job_complete.assert_any_call(synapse_with_failed_execution.finished_executions[0])
        mock_patch_job_complete.assert_any_call(synapse_with_failed_execution.finished_executions[1])

def test_job_is_recorded(scorer: Scorer, synapse: CircuitSynapse, compute_request: ComputeRequest, mock_axon):
    """Test that we call the function to record the job when success is True and not rate_limited"""
    with patch.object(scorer, "_record_execution") as mock_record_execution:
        scorer.process_miner_responses([synapse], BasicMiner(hotkey="miner_hotkey_1", uid=2, axon=mock_axon), compute_request)
        mock_record_execution.assert_called_once_with("miner_hotkey_1", compute_request.execution_id, compute_request.shots)

def test_no_completed_jobs(scorer: Scorer, synapse: CircuitSynapse, compute_request: ComputeRequest, mock_axon):
    """Test that if there are no completed jobs, we do not update last circuit, record the time received, or call patch job complete"""
    synapse.finished_executions = []
    with patch.object(scorer._metrics, "upsert_last_circuit") as mock_upsert_last_circuit, \
        patch.object(scorer, "_record_time_received") as mock_record_time_received, \
        patch.object(scorer, "_patch_job_complete") as mock_patch_job_complete:
        scorer.process_miner_responses([synapse], BasicMiner(hotkey="miner_hotkey_1", uid=2, axon=mock_axon), compute_request)
        mock_upsert_last_circuit.assert_not_called()
        mock_record_time_received.assert_not_called()
        mock_patch_job_complete.assert_not_called()

def test_completed_jobs_handled(scorer: Scorer, synapse: CircuitSynapse, compute_request: ComputeRequest, mock_axon):
    """Test that completed jobs lead to calls to update last circuit and record time received"""
    with patch.object(scorer._metrics, "upsert_last_circuit") as mock_upsert_last_circuit, \
        patch.object(scorer, "_record_time_received") as mock_record_time_received, \
        patch.object(scorer, "_patch_job_complete") as mock_patch_job_complete:
        # Patch _patch_job_running to avoid real HTTP calls
        scorer.process_miner_responses([synapse], BasicMiner(hotkey="miner_hotkey_1", uid=2, axon=mock_axon), compute_request)
        mock_upsert_last_circuit.assert_called_once_with("miner_hotkey_1", synapse.last_circuit)
        mock_record_time_received.assert_called_once_with("miner_hotkey_1", synapse.finished_executions[0].execution_id)
        mock_patch_job_complete.assert_called_once_with(synapse.finished_executions[0])

def test_patch_job_rejected_called_on_exception(scorer: Scorer, synapse: CircuitSynapse, compute_request: ComputeRequest, mock_axon):
    """Test that if an exception occurs in processing, it is logged and does not raise."""
    # Force an exception in _record_execution
    with patch.object(scorer, "_record_execution", side_effect=Exception("fail")), \
        patch.object(scorer, "_patch_job_rejected") as mock_patch_job_rejected, \
        patch("qbittensor.validator.reward.score.bt.logging") as mock_logging:
        scorer.process_miner_responses([synapse], BasicMiner(hotkey="miner_hotkey_1", uid=2, axon=mock_axon), compute_request)
        # Should not call _patch_job_rejected, but should log error
        mock_patch_job_rejected.assert_not_called()
        assert mock_logging.error.called

def test_patch_job_rejected_handles_patch_exception(scorer: Scorer):
    """Test _patch_job_rejected logs when patch raises an exception."""
    with patch.object(scorer.request_manager, "patch", side_effect=Exception("patch failed")), \
            patch("qbittensor.validator.reward.score.bt.logging") as mock_logging:
        scorer._patch_job_rejected("jobid", "msg")
        assert mock_logging.trace.called
        assert "patch failed" in str(mock_logging.trace.call_args)

def test_patch_job_complete_handles_patch_exception(scorer: Scorer):
    """Test _patch_job_complete logs when patch raises an exception."""
    job = ExecutionData(execution_id="jobid", shots=1, upload_data_id="dataid", status=ExecutionStatus.FAILED, errorMessage="error", execution_data={"provider_job_id": "provider_job_123"})
    with patch.object(scorer.request_manager, "patch", side_effect=Exception("patch failed")), \
            patch("qbittensor.validator.reward.score.bt.logging") as mock_logging:
        scorer._patch_job_complete(job)
        assert mock_logging.trace.called
        assert "patch failed" in str(mock_logging.trace.call_args)

def test_update_last_circuit_table_success(scorer: Scorer, synapse: CircuitSynapse):
    """Test _update_last_circuit_table inserts data without exception."""
    with patch.object(scorer.database_manager, "query_and_commit_with_values") as mock_query:
        scorer._update_last_circuit_table(synapse, "miner_hotkey_1")
        mock_query.assert_called_once()
    with patch.object(scorer.database_manager, "query_and_commit_with_values", side_effect=Exception("fail")), \
        patch("qbittensor.validator.reward.score.bt.logging") as mock_logging:
        scorer._update_last_circuit_table(synapse, "miner_hotkey_1")
        assert mock_logging.debug.called

def test_record_execution_and_time_received_calls_metrics(scorer: Scorer):
    """Test _record_execution and _record_time_received call metrics methods."""
    with patch.object(scorer._metrics, "insert_job_sent") as mock_insert_job_sent, \
        patch.object(scorer._metrics, "update_time_received") as mock_update_time_received:
        scorer._record_execution("hotkey", "jobid", 5)
        scorer._record_time_received("hotkey", "jobid")
        assert mock_insert_job_sent.called
        assert mock_update_time_received.called
