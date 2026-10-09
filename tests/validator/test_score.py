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
from qbittensor.protocol import CircuitSynapse, ExecutionData
from qbittensor.utils.request.jwt_manager import JWT
from qbittensor.utils.time import timestamp
from qbittensor.validator.compute_request.compute_request import ComputeRequest
from qbittensor.validator.miner_manager.next_miner import BasicMiner
from qbittensor.validator.reward.score import Scorer
from qbittensor.validator.utils.execution_status import ExecutionStatus
from tests.miner.constants import VALIDATOR_TEST_DB_NAME
from tests.test_utils import clean_up_validator_db, get_mock_metagraph
from unittest.mock import Mock, patch


# ---------
# Fixtures
# ---------

@pytest.fixture(scope="module", autouse=True)
def teardown():
    """Runs once after each test."""
    yield  # tests run here
    # cleanup logic after all tests
    clean_up_validator_db()


@pytest.fixture
def scorer(monkeypatch):
    database_manager = DatabaseManager(VALIDATOR_TEST_DB_NAME)
    with database_manager.lock:
        try:
            database_manager.query_and_commit("DELETE FROM inflight_execution")
        except Exception:
            pass

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
    metagraph: bt.Metagraph = get_mock_metagraph(5)
    # Scorer now requires telemetry and job clients; provide minimal
    from unittest.mock import Mock
    from qbittensor.utils.services.telemetry import TelemetryService
    from qbittensor.utils.services.job import JobClient
    # Use mocks for clients
    tel = Mock(spec=TelemetryService)
    jobc = Mock(spec=JobClient)
    return Scorer(database_manager, metagraph, telemetry_service=tel, job_client=jobc)


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


# ------
# Tests
# ------

def test_synapse_success_false(scorer: Scorer, synapse: CircuitSynapse, compute_request: ComputeRequest, mock_axon):
    """Test that we call the function to reject the job when success is False"""
    synapse.success = False
    with patch.object(scorer, "_patch_job_rejected") as mock_patch_job_rejected:
        scorer.process_miner_responses(
            [synapse],
            BasicMiner(
                hotkey="miner_hotkey_1",
                uid=2,
                axon=mock_axon),
            compute_request)
        mock_patch_job_rejected.assert_called_once_with(synapse.execution_id, "Miner did not respond")


def test_synapse_rate_limited(scorer: Scorer, synapse: CircuitSynapse, compute_request: ComputeRequest, mock_axon):
    """Test that we call the function to reject the job when rate_limited is True"""
    synapse.rate_limited = True
    with patch.object(scorer, "_patch_job_rejected") as mock_patch_job_rejected:
        scorer.process_miner_responses(
            [synapse],
            BasicMiner(
                hotkey="miner_hotkey_1",
                uid=2,
                axon=mock_axon),
            compute_request)
        mock_patch_job_rejected.assert_called_once_with(synapse.execution_id, "Miner is rate limiting")


def test_synapse_with_failed_execution(
        scorer: Scorer,
        synapse_with_failed_execution: CircuitSynapse,
        compute_request: ComputeRequest,
        mock_axon):
    """Test that we call the function to reject the job for the failed execution and complete for the successful ones"""
    with patch.object(scorer, "_patch_job_rejected", return_value=True) as mock_patch_job_rejected, \
            patch.object(scorer, "_patch_job_complete", return_value=True) as mock_patch_job_complete:
        scorer.process_miner_responses(
            [synapse_with_failed_execution],
            BasicMiner(
                hotkey="miner_hotkey_1",
                uid=2,
                axon=mock_axon),
            compute_request)

        mock_patch_job_rejected.assert_called_once_with(
            synapse_with_failed_execution.finished_executions[2].execution_id,
            "Some error occurred",
            synapse_with_failed_execution.finished_executions[2].execution_data
        )
        assert mock_patch_job_complete.call_count == 2
        mock_patch_job_complete.assert_any_call(
            synapse_with_failed_execution.finished_executions[0], "miner_hotkey_1")
        mock_patch_job_complete.assert_any_call(
            synapse_with_failed_execution.finished_executions[1], "miner_hotkey_1")


def test_job_is_recorded(scorer: Scorer, synapse: CircuitSynapse, compute_request: ComputeRequest, mock_axon):
    """Test that we call the function to record the job when success is True and not rate_limited"""
    with patch.object(scorer, "_record_execution") as mock_record_execution:
        scorer.process_miner_responses(
            [synapse],
            BasicMiner(
                hotkey="miner_hotkey_1",
                uid=2,
                axon=mock_axon),
            compute_request)
        mock_record_execution.assert_called_once_with(
            "miner_hotkey_1", compute_request.execution_id, compute_request.shots)


def test_no_completed_jobs(scorer: Scorer, synapse: CircuitSynapse, compute_request: ComputeRequest, mock_axon):
    """Test that if there are no completed jobs, we do not update last circuit, record the time received, or call patch job complete"""
    synapse.finished_executions = []
    with patch.object(scorer._metrics, "upsert_last_circuit") as mock_upsert_last_circuit, \
            patch.object(scorer, "_record_time_received") as mock_record_time_received, \
            patch.object(scorer, "_patch_job_complete") as mock_patch_job_complete:
        scorer.process_miner_responses(
            [synapse],
            BasicMiner(
                hotkey="miner_hotkey_1",
                uid=2,
                axon=mock_axon),
            compute_request)
        mock_upsert_last_circuit.assert_not_called()
        mock_record_time_received.assert_not_called()
        mock_patch_job_complete.assert_not_called()


def test_completed_jobs_handled(scorer: Scorer, synapse: CircuitSynapse, compute_request: ComputeRequest, mock_axon):
    """Test that completed jobs lead to calls to update last circuit and record time received"""
    with patch.object(scorer._metrics, "upsert_last_circuit") as mock_upsert_last_circuit, \
            patch.object(scorer, "_record_time_received") as mock_record_time_received, \
            patch.object(scorer, "_patch_job_complete", return_value=True) as mock_patch_job_complete:
        scorer.process_miner_responses(
            [synapse],
            BasicMiner(
                hotkey="miner_hotkey_1",
                uid=2,
                axon=mock_axon),
            compute_request)
        mock_upsert_last_circuit.assert_called_once_with("miner_hotkey_1", synapse.last_circuit)
        mock_record_time_received.assert_called_once_with("miner_hotkey_1", synapse.finished_executions[0].execution_id)
        mock_patch_job_complete.assert_called_once_with(
            synapse.finished_executions[0], "miner_hotkey_1")


def test_last_circuit_not_advanced_when_complete_patch_fails(
        scorer: Scorer, synapse: CircuitSynapse, compute_request: ComputeRequest, mock_axon):
    with patch.object(scorer._metrics, "upsert_last_circuit") as mock_upsert_last_circuit, \
            patch.object(scorer, "_patch_job_complete", return_value=False):
        scorer.process_miner_responses(
            [synapse],
            BasicMiner(
                hotkey="miner_hotkey_1",
                uid=2,
                axon=mock_axon),
            compute_request)
        mock_upsert_last_circuit.assert_not_called()


def test_patch_job_rejected_called_on_exception(
        scorer: Scorer,
        synapse: CircuitSynapse,
        compute_request: ComputeRequest,
        mock_axon):
    """Test that if an exception occurs in processing, it is logged and does not raise."""
    # Force an exception in _record_execution
    with patch.object(scorer, "_record_execution", side_effect=Exception("fail")), \
            patch.object(scorer, "_patch_job_rejected") as mock_patch_job_rejected, \
            patch("qbittensor.validator.reward.score.bt.logging") as mock_logging:
        scorer.process_miner_responses(
            [synapse],
            BasicMiner(
                hotkey="miner_hotkey_1",
                uid=2,
                axon=mock_axon),
            compute_request)
        # Should not call _patch_job_rejected, but should log error
        mock_patch_job_rejected.assert_not_called()
        assert mock_logging.error.called


def test_patch_job_rejected_handles_patch_exception(scorer: Scorer):
    """Test _patch_job_rejected logs when patch raises an exception."""
    with patch.object(scorer.job_client, "patch_execution", side_effect=Exception("patch failed")), \
            patch("qbittensor.validator.reward.score.bt.logging") as mock_logging:
        assert scorer._patch_job_rejected("jobid", "msg") is False
        assert mock_logging.warning.called
        assert "patch failed" in str(mock_logging.warning.call_args)


def test_patch_job_complete_handles_patch_exception(scorer: Scorer):
    """Test _patch_job_complete logs when patch raises an exception."""
    job = ExecutionData(
        execution_id="jobid",
        shots=1,
        upload_data_id="dataid",
        status=ExecutionStatus.FAILED,
        errorMessage="error",
        execution_data={
            "provider_job_id": "provider_job_123"})
    with patch.object(scorer.job_client, "patch_execution", side_effect=Exception("patch failed")), \
            patch("qbittensor.validator.reward.score.bt.logging") as mock_logging:
        assert scorer._patch_job_complete(job) is False
        assert mock_logging.warning.called
        assert "patch failed" in str(mock_logging.warning.call_args)


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


class TestPatchJobRejectedSerialization:
    """Verify _patch_job_rejected calls patch_execution with Jobs status strings."""

    def test_execution_data_sent_as_dict(self, scorer: Scorer):
        """_patch_job_rejected calls with status Failed and the message."""
        exec_data = {"jobId": "aws:rigetti:qpu:ankaa-3-d557-qjob-abc123"}
        with patch.object(scorer.job_client, "patch_execution") as mock_patch:
            scorer._patch_job_rejected("exec-001", "qasm3 conversion error", exec_data)
            mock_patch.assert_called_once_with(
                "exec-001",
                {
                    "status": "Failed",
                    "message": "qasm3 conversion error",
                    "execution_data": exec_data,
                },
            )

    def test_execution_data_defaults_to_empty_dict(self, scorer: Scorer):
        """Calls with correct status/msg even without execution_data."""
        with patch.object(scorer.job_client, "patch_execution") as mock_patch:
            scorer._patch_job_rejected("exec-002", "Miner reported failure")
            mock_patch.assert_called_once_with(
                "exec-002",
                {
                    "status": "Failed",
                    "message": "Miner reported failure",
                    "execution_data": {},
                },
            )

    def test_execution_data_none_becomes_empty_dict(self, scorer: Scorer):
        """Calls correctly when None passed."""
        with patch.object(scorer.job_client, "patch_execution") as mock_patch:
            scorer._patch_job_rejected("exec-003", "error msg", None)
            mock_patch.assert_called_once_with(
                "exec-003",
                {
                    "status": "Failed",
                    "message": "error msg",
                    "execution_data": {},
                },
            )

    def test_error_message_preserved_in_body(self, scorer: Scorer):
        """The error message is passed correctly."""
        error = "Failed to convert 'qasm3' to 'braket'"
        with patch.object(scorer.job_client, "patch_execution") as mock_patch:
            scorer._patch_job_rejected("exec-004", error, {"jobId": "j1"})
            mock_patch.assert_called_once_with(
                "exec-004",
                {
                    "status": "Failed",
                    "message": error,
                    "execution_data": {"jobId": "j1"},
                },
            )

    def test_nested_proof_is_omitted_so_failure_can_land(self, scorer: Scorer):
        """Jobs requires upload_id whenever a proof is present, including Failed."""
        original = {
            "stage": "submit",
            "proof": {"statement": "pot.job.v1\njob_id=j1", "signature": "sig"},
        }
        with patch.object(scorer.job_client, "patch_execution") as mock_patch:
            scorer._patch_job_rejected("exec-proof", "Invalid private-job proof", original)
            mock_patch.assert_called_once_with(
                "exec-proof",
                {
                    "status": "Failed",
                    "message": "Invalid private-job proof",
                    "execution_data": {"stage": "submit"},
                },
            )
        assert "proof" in original

    def test_complete_rejects_when_ca_proof_invalid(self, scorer: Scorer):
        job = ExecutionData(
            execution_id="exec-006",
            shots=1,
            upload_data_id="upload-1",
            status=ExecutionStatus.COMPLETED,
            execution_data={
                "proof": {
                    "statement": "pot.job.v1\njob_id=j1",
                    "signature": "sig",
                    "certificate_pem": "pem",
                }
            },
        )
        scorer.job_client.verify_ca_proof = Mock(return_value=False)
        with patch.object(scorer.job_client, "patch_execution") as mock_patch:
            with patch(
                "qbittensor.validator.reward.score.ban_miner"
            ) as mock_ban:
                assert scorer._patch_job_complete(job, "hk-bad") is False
            mock_ban.assert_called_once()
            assert mock_ban.call_args.kwargs.get("hours") == 24
            assert mock_ban.call_args.args[1] == "hk-bad"
            scorer.telemetry_service.vali_record_ban.assert_called()
            scorer.telemetry_service.vali_record_proof_fail.assert_called()
            mock_patch.assert_called_once_with(
                "exec-006",
                {
                    "status": "Failed",
                    "message": "Invalid private-job proof",
                    "execution_data": {},
                },
            )
            assert "proof" in job.execution_data

    def test_complete_verifies_proof_even_if_dry_run_flag_present(self, scorer: Scorer):
        job = ExecutionData(
            execution_id="exec-007",
            shots=1,
            upload_data_id="upload-1",
            status=ExecutionStatus.COMPLETED,
            execution_data={
                "dry_run": True,
                "proof": {
                    "statement": "pot.job.v1\njob_id=j1",
                    "signature": "sig",
                    "certificate_pem": "pem",
                },
            },
        )
        scorer.job_client.verify_ca_proof = Mock(return_value=False)
        with patch.object(scorer.job_client, "patch_execution") as mock_patch:
            assert scorer._patch_job_complete(job, "hk-dry") is False
        scorer.job_client.verify_ca_proof.assert_called_once()
        fail_body = mock_patch.call_args[0][1]
        assert fail_body["message"] == "Invalid private-job proof"
        assert fail_body["execution_data"] == {"dry_run": True}
        assert "proof" in job.execution_data

    def test_stale_public_lease_bans_miner_twenty_four_hours(self, scorer: Scorer):
        scorer._inflight_seen["exec-lease"] = ("hk-late", 0.0)
        scorer._assigned.add("exec-lease")
        scorer.job_client.patch_execution.return_value = {"updated": True}
        with patch(
            "qbittensor.validator.reward.score.ban_miner"
        ) as mock_ban:
            n = scorer.expire_stale_leases(now=45 * 60 + 1)
        assert n == 1
        mock_ban.assert_called_once()
        assert mock_ban.call_args.kwargs.get("hours") == 24
        assert mock_ban.call_args.args[1] == "hk-late"
        assert mock_ban.call_args.args[2] == "lease_expired"
        body = scorer.job_client.patch_execution.call_args[0][1]
        assert body["message"] == "lease_expired"
        assert "exec-lease" not in scorer._inflight_seen
        assert "exec-lease" not in scorer._assigned
        scorer.telemetry_service.vali_record_lease_expired.assert_called_once()
        scorer.telemetry_service.vali_record_ban.assert_called()
        ban_tel = scorer.telemetry_service.vali_record_ban.call_args
        assert ban_tel.args[1] == "lease_expired"

    def test_observer_lease_silence_bans_without_patch(self, scorer: Scorer):
        scorer._inflight_seen["exec-seen"] = ("hk-other", 0.0)
        with patch(
            "qbittensor.validator.reward.score.ban_miner"
        ) as mock_ban:
            n = scorer.expire_stale_leases(now=45 * 60 + 1)
        assert n == 1
        mock_ban.assert_called_once()
        scorer.job_client.patch_execution.assert_not_called()
        assert "exec-seen" not in scorer._inflight_seen

    def test_fresh_lease_patch_does_not_ban_the_assigner(self, scorer: Scorer):
        scorer._inflight_seen["exec-live"] = ("hk-assign", 0.0)
        scorer._assigned.add("exec-live")
        scorer.job_client.patch_execution.return_value = {
            "updated": False,
            "reason": "lease_fresh",
        }
        with patch(
            "qbittensor.validator.reward.score.ban_miner"
        ) as mock_ban:
            n = scorer.expire_stale_leases(now=45 * 60 + 1)
        assert n == 0
        mock_ban.assert_not_called()
        assert "exec-live" in scorer._assigned
        assert "exec-live" in scorer._inflight_seen

    def test_replayed_private_proof_bans_miner_twenty_four_hours(self, scorer: Scorer):
        from qbittensor.utils.services.exceptions import JobApiError

        job = ExecutionData(
            execution_id="exec-replay",
            shots=1,
            upload_data_id="upload-1",
            status=ExecutionStatus.COMPLETED,
            execution_data={
                "proof": {
                    "statement": "pot.job.v1\njob_id=j1",
                    "signature": "sig-reuse",
                    "certificate_pem": "pem",
                }
            },
        )
        scorer.job_client.verify_ca_proof = Mock(return_value=True)
        scorer.job_client.patch_execution = Mock(
            side_effect=[
                JobApiError(
                    "Failed to patch execution exec-replay",
                    status_code=400,
                    response_text='{"message":"Private-job proof is already bound to another execution"}',
                ),
                None,
            ]
        )
        with patch(
            "qbittensor.validator.reward.score.ban_miner"
        ) as mock_ban:
            assert scorer._patch_job_complete(job, "hk-replay") is False
        mock_ban.assert_called_once()
        assert mock_ban.call_args.kwargs.get("hours") == 24
        assert mock_ban.call_args.args[1] == "hk-replay"
        assert mock_ban.call_args.args[2] == "proof_replay"
        scorer.telemetry_service.vali_record_ban.assert_called()
        scorer.telemetry_service.vali_record_proof_fail.assert_called()
        fail_body = scorer.job_client.patch_execution.call_args_list[1][0][1]
        assert fail_body["status"] == "Failed"
        assert fail_body["message"] == "Invalid private-job proof"
        assert fail_body["execution_data"] == {}
        assert "upload_id" not in fail_body

    def test_complete_sends_completed_status_string(self, scorer: Scorer):
        job = ExecutionData(
            execution_id="exec-005",
            shots=1,
            upload_data_id="upload-1",
            status=ExecutionStatus.COMPLETED,
            execution_data={"provider_job_id": "p1"},
        )
        with patch.object(scorer.job_client, "patch_execution") as mock_patch:
            assert scorer._patch_job_complete(job) is True
            mock_patch.assert_called_once_with(
                "exec-005",
                {
                    "status": "Completed",
                    "upload_id": "upload-1",
                    "execution_data": {"provider_job_id": "p1"},
                },
            )

    def test_queried_miner_drop_patches_inflight(self, scorer: Scorer, mock_axon):
        from qbittensor.protocol import COLLECT_SYNAPSE_ID

        miner = BasicMiner(hotkey="hk-drop", uid=1, axon=mock_axon)
        req = ComputeRequest(
            execution_id=COLLECT_SYNAPSE_ID,
            shots=10,
            input_data_url="x",
            configuration_data={},
        )
        first = CircuitSynapse(
            execution_id=COLLECT_SYNAPSE_ID,
            input_data_url="x",
            shots=10,
            configuration_data={},
            last_circuit="0",
            success=True,
            active_executions=[
                ExecutionData(
                    execution_id="inflight-1",
                    shots=10,
                    upload_data_id="",
                    execution_data={},
                    status=ExecutionStatus.RUNNING,
                )
            ],
            finished_executions=[],
        )
        scorer.process_miner_responses([first], miner, req)
        second = CircuitSynapse(
            execution_id=COLLECT_SYNAPSE_ID,
            input_data_url="x",
            shots=10,
            configuration_data={},
            last_circuit="0",
            success=True,
            active_executions=[],
            finished_executions=[],
        )
        with patch.object(scorer, "_patch_job_rejected", return_value=True) as rejected:
            scorer.process_miner_responses([second], miner, req)
        rejected.assert_called()
        assert rejected.call_args[0][0] == "inflight-1"
        assert "Dropped" in rejected.call_args[0][1]
        scorer.telemetry_service.vali_record_dropped_inflight.assert_called()
        drop_args = scorer.telemetry_service.vali_record_dropped_inflight.call_args
        assert drop_args.args[1] == "inflight-1"


def test_inflight_hotkeys_unions_active_and_lease(scorer: Scorer):
    scorer._last_active["hk-a"] = {"e1"}
    scorer._last_active["hk-empty"] = set()
    scorer._inflight_seen["e2"] = ("hk-b", 1.0)
    assert scorer.inflight_hotkeys() == {"hk-a", "hk-b"}


def test_inflight_survives_restart(scorer: Scorer):
    scorer._record_execution("hk", "exec-keep", 1)
    seen = scorer._inflight_seen["exec-keep"][1]
    again = Scorer(
        scorer.database_manager,
        scorer.metagraph,
        telemetry_service=scorer.telemetry_service,
        job_client=scorer.job_client,
    )
    assert "exec-keep" in again._assigned
    assert again._inflight_seen["exec-keep"][0] == "hk"
    assert again._inflight_seen["exec-keep"][1] == pytest.approx(seen)

    again._note_inflight("hk-obs", "exec-obs")
    third = Scorer(
        scorer.database_manager,
        scorer.metagraph,
        telemetry_service=scorer.telemetry_service,
        job_client=scorer.job_client,
    )
    assert "exec-obs" in third._inflight_seen
    assert "exec-obs" not in third._assigned
    assert "exec-keep" in third._assigned

    third._clear_inflight("exec-keep")
    fourth = Scorer(
        scorer.database_manager,
        scorer.metagraph,
        telemetry_service=scorer.telemetry_service,
        job_client=scorer.job_client,
    )
    assert "exec-keep" not in fourth._inflight_seen
    assert "exec-keep" not in fourth._assigned
    assert "exec-obs" in fourth._inflight_seen
