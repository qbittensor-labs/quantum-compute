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

import asyncio

import numpy as np
import pytest
from unittest.mock import Mock
from neurons.miner import Miner
from qbittensor.bt_compat import TerminalInfo
from qbittensor.protocol import CircuitSynapse, ExecutionData
import bittensor as bt


@pytest.fixture
def setup_env(monkeypatch):
    """Set up environment for testing."""
    monkeypatch.setenv("PROVIDER", "mock")
    monkeypatch.setenv("JOB_SERVER_URL", "http://127.0.0.1:9999")


@pytest.fixture
def mock_bittensor_components(monkeypatch):
    """Mock only the essential bittensor network components."""
    monkeypatch.setattr(bt.logging, "set_config", Mock())

    mock_wallet = Mock()
    mock_wallet.hotkey = Mock(ss58_address="test_miner_hotkey")

    mock_subtensor = Mock()

    mock_metagraph = Mock()
    mock_metagraph.hotkeys = ["test_miner_hotkey", "validator_hotkey"]
    mock_metagraph.last_update = {0: 0, 1: 0}
    mock_metagraph.S = [1000.0, 2000.0]

    from tests.bt_v11_helpers import wire_v11_subtensor
    wire_v11_subtensor(
        mock_subtensor,
        mock_metagraph,
        hotkeys=["test_miner_hotkey", "validator_hotkey"],
        netuid=1,
    )

    mock_axon = Mock()
    mock_axon.attach = Mock()
    mock_axon.serve = Mock()
    mock_axon.start = Mock()
    mock_axon.stop = Mock()

    monkeypatch.setattr(bt, "Wallet", Mock(return_value=mock_wallet))
    monkeypatch.setattr(bt, "Subtensor", Mock(return_value=mock_subtensor))
    monkeypatch.setattr(bt, "Axon", Mock(return_value=mock_axon))

    return mock_wallet, mock_subtensor, mock_metagraph, mock_axon


@pytest.fixture
def miner(setup_env, mock_bittensor_components, monkeypatch):
    """Create a miner instance with mocked network components."""
    mock_config = Mock()
    mock_config.mock = False
    mock_config.netuid = 1
    mock_config.neuron = Mock(
        device="cpu",
        epoch_length=100,
        name="test_miner",
        dont_save_events=True
    )
    mock_config.wallet = Mock(name="test_wallet", hotkey="test_hotkey")
    mock_config.blacklist = Mock(
        force_validator_permit=True,
        allow_non_registered=False
    )
    mock_config.logging = Mock(
        debug=False,
        trace=False,
        info=False,
        logging_dir="/tmp/test_miners"
    )
    mock_config.subtensor = Mock(network="finney", endpoint="finney")
    # v11 Config.merge returns a new object; keep this mock as the active config.
    mock_config.merge = Mock(return_value=mock_config)

    monkeypatch.setattr(Miner, "config", Mock(return_value=mock_config))
    monkeypatch.setattr(Miner, "check_config", Mock())

    miner = Miner(config=mock_config)
    return miner


def _caller(hotkey: str) -> CircuitSynapse:
    synapse = CircuitSynapse(
        execution_id="collect",
        shots=1,
        configuration_data={},
        input_data_url="http://qasm",
        last_circuit="1970-01-01 00:00:00",
        finished_executions=[],
    )
    synapse.dendrite = TerminalInfo(hotkey=hotkey)
    return synapse


def test_blacklist_rejects_registered_hotkey_without_validator_permit(miner):
    miner.metagraph.hotkeys = ["miner_hk", "vali_hk"]
    miner.metagraph.S = [10.0, 20.0]
    miner.metagraph.validator_permit = [False, True]
    miner.config.blacklist.force_validator_permit = True

    blocked, reason = asyncio.run(miner.blacklist(_caller("miner_hk")))

    assert blocked is True
    assert "validator permit" in reason


def test_blacklist_accepts_validator_permit(miner):
    miner.metagraph.hotkeys = ["miner_hk", "vali_hk"]
    miner.metagraph.S = [10.0, 20.0]
    miner.metagraph.validator_permit = np.array([False, True])
    miner.config.blacklist.force_validator_permit = True

    blocked, reason = asyncio.run(miner.blacklist(_caller("vali_hk")))

    assert blocked is False
    assert "vali_hk" in reason


def test_blacklist_allows_non_permit_when_flag_disabled(miner):
    miner.metagraph.hotkeys = ["miner_hk", "vali_hk"]
    miner.metagraph.S = [10.0, 20.0]
    miner.metagraph.validator_permit = [False, True]
    miner.config.blacklist.force_validator_permit = False

    blocked, _reason = asyncio.run(miner.blacklist(_caller("miner_hk")))

    assert blocked is False


def test_forward_submits_new_job(miner, monkeypatch):
    """Test that forward() correctly submits a new job."""
    submitted_jobs = []

    def mock_submit(**kwargs):
        submitted_jobs.append(kwargs)

    monkeypatch.setattr(miner.jobs, "submit", mock_submit)

    synapse = CircuitSynapse(
        execution_id="12345",
        shots=999,
        configuration_data={"shots": 100, "n": 2},
        input_data_url="http://qasm",
        last_circuit="1970-01-01 00:00:00",
        finished_executions=[]
    )

    monkeypatch.setattr(miner, "_get_validator_hotkey", lambda syn: "validator_hotkey_123")
    monkeypatch.setattr(miner, "_job_is_new", lambda eid: True)

    class Resp:
        def __init__(self):
            self.status_code = 200

        def raise_for_status(self):
            return None
    monkeypatch.setattr("requests.get", lambda url, timeout=5: Resp())

    result = miner.forward(synapse)
    miner.jobs.join_submits(2)

    assert result is synapse
    assert synapse.success
    assert len(submitted_jobs) == 1
    assert submitted_jobs[0]["execution_id"] == "12345"
    assert submitted_jobs[0]["input_data_url"] == synapse.input_data_url
    assert submitted_jobs[0]["shots"] == 100
    assert submitted_jobs[0]["configuration_data"] == {"shots": 100, "n": 2}
    assert submitted_jobs[0]["validator_hotkey"] == "validator_hotkey_123"


def test_forward_rejects_duplicate_job(miner, monkeypatch):
    """Test that forward() doesn't re-submit existing jobs."""
    submitted_jobs = []
    monkeypatch.setattr(miner.jobs, "submit", lambda **kwargs: submitted_jobs.append(kwargs))

    synapse = CircuitSynapse(
        execution_id="99999",
        shots=50,
        configuration_data={},
        input_data_url="http://qasm",
        last_circuit="1970-01-01 00:00:00",
        finished_executions=[]
    )

    monkeypatch.setattr(miner, "_get_validator_hotkey", lambda syn: "validator_456")
    monkeypatch.setattr(miner, "_job_is_new", lambda eid: False)

    result = miner.forward(synapse)

    # NOT submit duplicate
    assert len(submitted_jobs) == 0
    assert result.success


def test_forward_handles_missing_dendrite(miner):
    """Test that forward() handles synapses without dendrite info."""
    synapse = CircuitSynapse(
        execution_id="77777",
        shots=10,
        configuration_data={},
        input_data_url="http://qasm",
        last_circuit="1970-01-01 00:00:00",
        finished_executions=[]
    )

    result = miner.forward(synapse)

    assert result is synapse
    assert synapse.success is False


def test_collect_sets_rate_limited_when_credits_are_low(miner, monkeypatch):
    """A broke miner still returns finished rows, and tells the validator not to class-claim."""
    from qbittensor.protocol import COLLECT_SYNAPSE_ID

    synapse = CircuitSynapse(
        execution_id=COLLECT_SYNAPSE_ID,
        shots=1,
        configuration_data={},
        input_data_url="http://qasm",
        last_circuit="1970-01-01 00:00:00",
        finished_executions=[],
    )
    monkeypatch.setattr(miner, "_get_validator_hotkey", lambda syn: "validator_789")
    adapter = Mock()
    adapter.should_rate_limit_request.return_value = True
    miner.jobs.adapter = adapter
    recorded = []
    monkeypatch.setattr(
        miner.telemetry_service,
        "miner_record_rate_limited",
        lambda eid: recorded.append(eid),
    )

    result = miner.forward(synapse)

    assert result.rate_limited is True
    assert result.success is True
    assert recorded == [COLLECT_SYNAPSE_ID]
    adapter.should_rate_limit_request.assert_called_once_with(shots=1)


def test_collect_stays_willing_when_credits_are_above_the_floor(miner, monkeypatch):
    from qbittensor.protocol import COLLECT_SYNAPSE_ID

    synapse = CircuitSynapse(
        execution_id=COLLECT_SYNAPSE_ID,
        shots=1,
        configuration_data={},
        input_data_url="http://qasm",
        last_circuit="1970-01-01 00:00:00",
        finished_executions=[],
    )
    monkeypatch.setattr(miner, "_get_validator_hotkey", lambda syn: "validator_789")
    adapter = Mock()
    adapter.should_rate_limit_request.return_value = False
    miner.jobs.adapter = adapter

    result = miner.forward(synapse)

    assert not result.rate_limited
    assert result.success is True


def test_forward_applies_rate_limiting(miner, monkeypatch):
    """Test that forward() respects rate limiting."""
    synapse = CircuitSynapse(
        execution_id="33333",
        shots=1000,
        configuration_data={},
        input_data_url="http://qasm",
        last_circuit="1970-01-01 00:00:00",
        finished_executions=[]
    )

    monkeypatch.setattr(miner, "_get_validator_hotkey", lambda syn: "validator_789")

    monkeypatch.setattr(miner, "_rate_limit", lambda: True)
    monkeypatch.setattr(miner, "_job_is_new", lambda eid: True)

    submitted = []
    monkeypatch.setattr(miner.jobs, "submit", lambda **kwargs: submitted.append(kwargs))

    result = miner.forward(synapse)

    assert result is synapse
    assert synapse.rate_limited  # set rate limited flag
    assert len(submitted) == 0  # NOT submit when rate limited


def test_forward_adds_completed_circuits(miner, monkeypatch):
    """Test that forward() adds completed circuits to the response."""
    completed_circuits = [
        {"job_id": 111, "shots": 10, "solution_bitstring": "0011", "timestamp": "2024-01-01 12:00:00"},
        {"job_id": 222, "shots": 20, "solution_bitstring": "1100", "timestamp": "2024-01-01 12:05:00"}
    ]

    def mock_get_completed(last_update):
        from qbittensor.validator.utils.execution_status import ExecutionStatus
        jobs = [
            ExecutionData(
                execution_id=str(
                    c["job_id"]),
                shots=c["shots"],
                upload_data_id="rid",
                execution_data=None,
                status=ExecutionStatus.COMPLETED,
                errorMessage=None) for c in completed_circuits]
        return jobs, "2024-01-01 12:05:00"

    monkeypatch.setattr(miner, "_get_finished_executions", mock_get_completed)

    synapse = CircuitSynapse(
        execution_id="88888",
        shots=5,
        configuration_data={},
        input_data_url="http://qasm",
        last_circuit="2024-01-01 11:00:00",
        finished_executions=[]
    )

    monkeypatch.setattr(miner, "_get_validator_hotkey", lambda syn: "validator_xyz")
    monkeypatch.setattr(miner, "_job_is_new", lambda job_id: False)

    result = miner.forward(synapse)

    assert len(result.finished_executions) == 2
    assert result.finished_executions[0].execution_id == "111"
    assert result.finished_executions[1].execution_id == "222"
    assert result.last_circuit == "2024-01-01 12:05:00"


def test_forward_sets_capabilities_from_adapter(miner, monkeypatch):
    miner.jobs.adapter = Mock()
    miner.jobs.adapter.list_public_classes.return_value = ["quantumrings:qasm3"]
    synapse = CircuitSynapse(
        execution_id="88888",
        shots=5,
        configuration_data={},
        input_data_url="http://qasm",
        last_circuit="2024-01-01 11:00:00",
        finished_executions=[],
    )
    monkeypatch.setattr(miner, "_get_validator_hotkey", lambda syn: "validator_xyz")
    monkeypatch.setattr(miner, "_job_is_new", lambda job_id: False)
    result = miner.forward(synapse)
    assert result.capabilities == ["quantumrings:qasm3"]


def test_forward_sets_capabilities_from_env_when_adapter_missing(miner, monkeypatch):
    monkeypatch.setenv("PUBLIC_BACKEND_CLASSES", "ionq:forte-1, quantumrings:qasm3")
    miner.jobs.adapter = None
    synapse = CircuitSynapse(
        execution_id="77777",
        shots=10,
        configuration_data={},
        input_data_url="http://qasm",
        last_circuit="1970-01-01 00:00:00",
        finished_executions=[],
    )
    result = miner.forward(synapse)
    assert result.capabilities == ["ionq:forte-1", "quantumrings:qasm3"]


def test_forward_capabilities_default_empty(miner):
    miner.jobs.adapter = None
    synapse = CircuitSynapse(
        execution_id="77777",
        shots=10,
        configuration_data={},
        input_data_url="http://qasm",
        last_circuit="1970-01-01 00:00:00",
        finished_executions=[],
    )
    result = miner.forward(synapse)
    assert result.capabilities == []
