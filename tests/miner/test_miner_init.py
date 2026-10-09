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

from unittest.mock import Mock
import bittensor as bt
from neurons.miner import Miner
from tests.bt_v11_helpers import wire_v11_subtensor


def _wire_mock_config(mock_config: Mock) -> Mock:
    """v11 Config.merge returns a new object; keep tests on the same mock."""
    mock_config.merge = Mock(return_value=mock_config)
    return mock_config


def test_miner_initializes_with_mock_components(monkeypatch):
    """Test that miner can initialize with mocked bittensor components."""
    monkeypatch.setenv("PROVIDER", "mock")
    monkeypatch.setattr(bt.logging, "set_config", Mock())

    mock_wallet = Mock()
    mock_wallet.hotkey = Mock(ss58_address="test_hotkey")

    mock_subtensor = Mock()
    mock_metagraph = Mock()
    mock_metagraph.hotkeys = ["test_hotkey"]
    mock_metagraph.last_update = {0: 0}
    adapted = wire_v11_subtensor(
        mock_subtensor, mock_metagraph, hotkeys=["test_hotkey"], netuid=1
    )

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
    mock_config.subtensor = Mock(network="finney", endpoint="finney")
    _wire_mock_config(mock_config)

    monkeypatch.setattr(bt, "Wallet", Mock(return_value=mock_wallet))
    monkeypatch.setattr(bt, "Subtensor", Mock(return_value=mock_subtensor))
    monkeypatch.setattr(bt, "Axon", Mock(return_value=mock_axon))
    monkeypatch.setattr(Miner, "config", Mock(return_value=mock_config))
    monkeypatch.setattr(Miner, "check_config", Mock())

    miner = Miner(config=mock_config)

    assert miner.wallet == mock_wallet
    assert miner.subtensor == mock_subtensor
    assert miner.metagraph is adapted
    assert miner.metagraph.hotkeys == ["test_hotkey"]
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
    mock_metagraph = Mock(hotkeys=["miner_hotkey_456"], last_update={0: 0})
    wire_v11_subtensor(
        mock_subtensor, mock_metagraph, hotkeys=["miner_hotkey_456"], netuid=1
    )

    mock_config = Mock()
    mock_config.mock = False
    mock_config.netuid = 1
    mock_config.neuron = Mock(device="cpu", epoch_length=100, name="test", dont_save_events=True)
    mock_config.wallet = Mock(name="w", hotkey="h")
    mock_config.blacklist = Mock(force_validator_permit=False, allow_non_registered=False)
    mock_config.logging = Mock(debug=False, logging_dir="/tmp")
    mock_config.subtensor = Mock(network="finney", endpoint="finney")
    _wire_mock_config(mock_config)

    monkeypatch.setattr(bt, "Wallet", Mock(return_value=mock_wallet))
    monkeypatch.setattr(bt, "Subtensor", Mock(return_value=mock_subtensor))
    monkeypatch.setattr(bt, "Axon", Mock(return_value=Mock()))
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
    mock_metagraph = Mock(hotkeys=["test"], last_update={0: 0})
    mock_subtensor = Mock()
    wire_v11_subtensor(mock_subtensor, mock_metagraph, hotkeys=["test"], netuid=1)

    mock_config = Mock(
        mock=False, netuid=1,
        neuron=Mock(device="cpu", epoch_length=100, name="test", dont_save_events=True),
        wallet=Mock(name="w", hotkey="h"),
        blacklist=Mock(force_validator_permit=False, allow_non_registered=False),
        logging=Mock(debug=False, logging_dir="/tmp"),
        subtensor=Mock(network="finney", endpoint="finney"),
    )
    _wire_mock_config(mock_config)

    monkeypatch.setattr(bt, "Wallet", Mock(return_value=mock_wallet))
    monkeypatch.setattr(bt, "Subtensor", Mock(return_value=mock_subtensor))
    monkeypatch.setattr(bt, "Axon", Mock(return_value=Mock()))
    monkeypatch.setattr(Miner, "config", Mock(return_value=mock_config))
    monkeypatch.setattr(Miner, "check_config", Mock())

    miner = Miner(config=mock_config)

    assert hasattr(miner, 'jobs')
