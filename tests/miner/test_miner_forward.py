import pytest
from unittest.mock import Mock
from neurons.miner import Miner
from qbittensor.protocol import CircuitSynapse, ExecutionData
import bittensor as bt


@pytest.fixture
def setup_env(monkeypatch):
    """Set up environment for testing."""
    monkeypatch.setenv("QBRAID_DRY_RUN", "1")
    monkeypatch.setenv("JOB_SERVER_URL", "http://127.0.0.1:9999")
    

@pytest.fixture  
def mock_bittensor_components(monkeypatch):
    """Mock only the essential bittensor network components."""
    monkeypatch.setattr(bt.logging, "set_config", Mock())
    
    mock_wallet = Mock()
    mock_wallet.hotkey = Mock(ss58_address="test_miner_hotkey")
    
    mock_subtensor = Mock()
    mock_subtensor.chain_endpoint = "mock_endpoint"
    mock_subtensor.is_hotkey_registered = Mock(return_value=True)
    
    mock_metagraph = Mock()
    mock_metagraph.hotkeys = ["test_miner_hotkey", "validator_hotkey"]
    mock_metagraph.last_update = {0: 0, 1: 0}
    mock_metagraph.S = [1000.0, 2000.0]
    mock_subtensor.metagraph = Mock(return_value=mock_metagraph)
    
    mock_axon = Mock()
    mock_axon.attach = Mock()
    mock_axon.serve = Mock()
    mock_axon.start = Mock()
    mock_axon.stop = Mock()
    
    monkeypatch.setattr(bt, "wallet", Mock(return_value=mock_wallet))
    monkeypatch.setattr(bt, "subtensor", Mock(return_value=mock_subtensor))
    monkeypatch.setattr(bt, "axon", Mock(return_value=mock_axon))
    
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
    
    monkeypatch.setattr(Miner, "config", Mock(return_value=mock_config))
    monkeypatch.setattr(Miner, "check_config", Mock())
    
    miner = Miner(config=mock_config)
    return miner


def test_forward_submits_new_job(miner, monkeypatch):
    """Test that forward() correctly submits a new job."""
    submitted_jobs = []
    
    def mock_submit(**kwargs):
        submitted_jobs.append(kwargs)
    
    monkeypatch.setattr(miner.jobs, "submit", mock_submit)
    
    synapse = CircuitSynapse(
        execution_id="12345",
        shots=100,
        configuration_data={},
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
    
    assert result is synapse
    assert synapse.success == True
    assert len(submitted_jobs) == 1
    assert submitted_jobs[0]["execution_id"] == "12345"
    assert submitted_jobs[0]["input_data_url"] == synapse.input_data_url
    assert submitted_jobs[0]["shots"] == 100
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
    assert result.success == True


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
    assert synapse.success == False


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
    
    monkeypatch.setattr(miner, "_rate_limit", lambda : True)
    monkeypatch.setattr(miner, "_job_is_new", lambda eid: True)
    
    submitted = []
    monkeypatch.setattr(miner.jobs, "submit", lambda **kwargs: submitted.append(kwargs))
    
    result = miner.forward(synapse)
    
    assert result is synapse
    assert synapse.rate_limited == True  # set rate limited flag
    assert len(submitted) == 0  # NOT submit when rate limited


def test_forward_adds_completed_circuits(miner, monkeypatch):
    """Test that forward() adds completed circuits to the response."""
    completed_circuits = [
        {"job_id": 111, "shots": 10, "solution_bitstring": "0011", "timestamp": "2024-01-01 12:00:00"},
        {"job_id": 222, "shots": 20, "solution_bitstring": "1100", "timestamp": "2024-01-01 12:05:00"}
    ]
    
    def mock_get_completed(last_update):
        from qbittensor.validator.utils.execution_status import ExecutionStatus
        jobs = [ExecutionData(execution_id=str(c["job_id"]), shots=c["shots"], upload_data_id="rid", execution_data=None, status=ExecutionStatus.COMPLETED, errorMessage=None) for c in completed_circuits]
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
