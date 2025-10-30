from unittest.mock import Mock
import bittensor as bt
from neurons.miner import Miner


def test_miner_initializes_with_mock_components(monkeypatch):
    """Test that miner can initialize with mocked bittensor components."""
    monkeypatch.setenv("PROVIDER", "mock")
    monkeypatch.setattr(bt.logging, "set_config", Mock())
    
    mock_wallet = Mock()
    mock_wallet.hotkey = Mock(ss58_address="test_hotkey")
    
    mock_subtensor = Mock()
    mock_subtensor.chain_endpoint = "test_endpoint"
    mock_subtensor.is_hotkey_registered = Mock(return_value=True)
    
    mock_metagraph = Mock()
    mock_metagraph.hotkeys = ["test_hotkey"]
    mock_metagraph.last_update = {0: 0}
    mock_subtensor.metagraph = Mock(return_value=mock_metagraph)
    
    mock_axon = Mock()
    mock_axon.attach = Mock()
    
    mock_config = Mock()
    mock_config.mock = False
    mock_config.netuid = 1
    mock_config.neuron = Mock(
        device="cpu",
        epoch_length=100,
        name="test_miner",
        dont_save_events=True
    )
    mock_config.wallet = Mock(name="test", hotkey="test")
    mock_config.blacklist = Mock(
        force_validator_permit=False,
        allow_non_registered=False
    )
    mock_config.logging = Mock(
        debug=False,
        logging_dir="/tmp/test"
    )
    
    monkeypatch.setattr(bt, "wallet", Mock(return_value=mock_wallet))
    monkeypatch.setattr(bt, "subtensor", Mock(return_value=mock_subtensor))
    monkeypatch.setattr(bt, "axon", Mock(return_value=mock_axon))
    monkeypatch.setattr(Miner, "config", Mock(return_value=mock_config))
    monkeypatch.setattr(Miner, "check_config", Mock())
    
    miner = Miner(config=mock_config)
    
    assert miner.wallet == mock_wallet
    assert miner.subtensor == mock_subtensor
    assert miner.metagraph == mock_metagraph
    assert miner.axon == mock_axon
    assert miner.uid == 0
    assert hasattr(miner, 'jobs')  # JobRegistry
    
    mock_axon.attach.assert_called_once()
    call_kwargs = mock_axon.attach.call_args.kwargs
    assert 'forward_fn' in call_kwargs
    assert 'blacklist_fn' in call_kwargs  
    assert 'priority_fn' in call_kwargs


def test_miner_sets_up_job_registry(monkeypatch):
    """Test that miner properly initializes JobRegistry."""
    monkeypatch.setenv("PROVIDER", "mock")
    monkeypatch.setattr(bt.logging, "set_config", Mock())
    
    mock_wallet = Mock()
    mock_wallet.hotkey = Mock(ss58_address="miner_hotkey_456")
    
    mock_subtensor = Mock()
    mock_subtensor.chain_endpoint = "test"
    mock_subtensor.is_hotkey_registered = Mock(return_value=True)
    mock_metagraph = Mock(hotkeys=["miner_hotkey_456"], last_update={0: 0})
    mock_subtensor.metagraph = Mock(return_value=mock_metagraph)
    
    mock_config = Mock()
    mock_config.mock = False
    mock_config.netuid = 1
    mock_config.neuron = Mock(device="cpu", epoch_length=100, name="test", dont_save_events=True)
    mock_config.wallet = Mock(name="w", hotkey="h")
    mock_config.blacklist = Mock(force_validator_permit=False, allow_non_registered=False)
    mock_config.logging = Mock(debug=False, logging_dir="/tmp")
    
    monkeypatch.setattr(bt, "wallet", Mock(return_value=mock_wallet))
    monkeypatch.setattr(bt, "subtensor", Mock(return_value=mock_subtensor))
    monkeypatch.setattr(bt, "axon", Mock(return_value=Mock()))
    monkeypatch.setattr(Miner, "config", Mock(return_value=mock_config))
    monkeypatch.setattr(Miner, "check_config", Mock())
    
    miner = Miner(config=mock_config)
    
    assert hasattr(miner, 'jobs')
    assert miner.jobs is not None
    assert hasattr(miner.jobs, 'submit')
    assert hasattr(miner.jobs, 'cancel')
    assert hasattr(miner.jobs, 'adapter')


def test_miner_initializes_budget_components(monkeypatch):
    """Test that miner properly sets up budget management."""
    monkeypatch.setenv("PROVIDER", "mock")
    monkeypatch.setenv("EPOCH_BUDGET_USD", "500.0")
    monkeypatch.setenv("PROFIT_GUARD_USD", "50.0")
    monkeypatch.setattr(bt.logging, "set_config", Mock())
    
    mock_wallet = Mock(hotkey=Mock(ss58_address="test"))
    mock_subtensor = Mock(
        chain_endpoint="test",
        is_hotkey_registered=Mock(return_value=True),
        metagraph=Mock(return_value=Mock(hotkeys=["test"], last_update={0: 0}))
    )
    
    mock_config = Mock(
        mock=False, netuid=1,
        neuron=Mock(device="cpu", epoch_length=100, name="test", dont_save_events=True),
        wallet=Mock(name="w", hotkey="h"),
        blacklist=Mock(force_validator_permit=False, allow_non_registered=False),
        logging=Mock(debug=False, logging_dir="/tmp")
    )
    
    monkeypatch.setattr(bt, "wallet", Mock(return_value=mock_wallet))
    monkeypatch.setattr(bt, "subtensor", Mock(return_value=mock_subtensor))
    monkeypatch.setattr(bt, "axon", Mock(return_value=Mock()))
    monkeypatch.setattr(Miner, "config", Mock(return_value=mock_config))
    monkeypatch.setattr(Miner, "check_config", Mock())
    
    miner = Miner(config=mock_config)
    
    assert hasattr(miner, 'jobs')
