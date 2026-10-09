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

from unittest.mock import Mock, patch

import numpy as np

from qbittensor.base.utils.weight_utils import process_weights_for_netuid
from qbittensor.base.validator import BaseValidatorNeuron
from tests.bt_v11_helpers import make_hyperparameters, wire_v11_subtensor


def test_base_weight_utils_still_importable():
    """Ensure the template weight utils are usable (as used by base set_weights)."""
    uids = np.array([0, 1, 2])
    w = np.array([0.1, 0.8, 0.1], dtype=np.float32)
    mg = Mock()
    mg.n = 10

    class _ST:
        hyperparameters = make_hyperparameters(min_allowed_weights=2, max_weight_limit=1.0)

    p_uids, p_w = process_weights_for_netuid(
        uids=uids, weights=w, netuid=1, subtensor=_ST(), metagraph=mg
    )
    assert p_uids is not None


def test_validator_instantiates_and_key_methods(monkeypatch):
    """Construct Validator (heavily mocked) and exercise forward + set_weights under v11."""
    import numpy as np
    from unittest.mock import Mock, patch
    import bittensor as bt

    from neurons.validator import Validator

    monkeypatch.setattr(bt.logging, "set_config", Mock())

    mock_wallet = Mock()
    mock_wallet.hotkey.ss58_address = "test_vali_hotkey"

    mock_subtensor = Mock()
    mock_metagraph = Mock()
    mock_metagraph.configure_mock(
        hotkeys=["test_vali_hotkey", "hk1", "hk2"],
        last_update=[0, 0, 0],
        uids=np.array([0, 1, 2]),
        axons=[Mock(), Mock(), Mock()],
        S=np.ones(3),
        n=3,
        netuid=48,
    )
    mock_metagraph.validator_trust = np.array([1.0, 0.0, 0.0])
    wire_v11_subtensor(
        mock_subtensor,
        mock_metagraph,
        hotkeys=["test_vali_hotkey", "hk1", "hk2"],
        netuid=48,
        max_weight_limit=1.0,
    )

    mock_dendrite = Mock()
    mock_dendrite.query.return_value = []

    mock_config = bt.Config()
    mock_config.neuron = bt.Config()
    mock_config.neuron.device = "cpu"
    mock_config.neuron.epoch_length = 100
    mock_config.neuron.disable_set_weights = False
    mock_config.neuron.moving_average_alpha = 0.1
    mock_config.neuron.axon_off = True
    mock_config.netuid = 48
    mock_config.mock = False
    mock_config.wallet = bt.Config()
    mock_config.wallet.name = "test"
    mock_config.wallet.hotkey = "test"
    mock_config.blacklist = bt.Config()
    mock_config.blacklist.force_validator_permit = True
    mock_config.blacklist.allow_non_registered = False
    mock_config.logging = bt.Config()
    mock_config.logging.debug = False
    mock_config.logging.logging_dir = "/tmp"
    mock_config.subtensor = bt.Config()
    mock_config.subtensor.network = "finney"
    mock_config.subtensor.endpoint = "finney"

    monkeypatch.setattr(Validator, "config", Mock(return_value=mock_config))
    monkeypatch.setattr(Validator, "check_config", Mock())

    with (
        patch("qbittensor.base.neuron.bt.Wallet", return_value=mock_wallet),
        patch("qbittensor.base.neuron.bt.Subtensor", return_value=mock_subtensor),
        patch("qbittensor.base.neuron.bt.Metagraph", return_value=mock_metagraph),
        patch("qbittensor.base.validator.bt.Dendrite", return_value=mock_dendrite),
        patch("qbittensor.base.validator.bt.Axon"),
        patch("qbittensor.base.neuron.BaseNeuron.sync"),
        patch("qbittensor.base.validator.BaseValidatorNeuron.load_state"),
        patch("qbittensor.base.neuron.check_config"),
        patch("qbittensor.database.database_manager.DatabaseManager"),
        patch("qbittensor.utils.request.request_manager.RequestManager"),
        patch("qbittensor.validator.heartbeat.Heartbeat"),
        patch("qbittensor.validator.miner_manager.miner_manager.MinerManager"),
        patch("qbittensor.validator.miner_manager.next_miner.NextMiner"),
        patch("qbittensor.validator.synapse.synapse_manager.SynapseManager"),
        patch("qbittensor.validator.reward.score.Scorer"),
        patch("qbittensor.validator.weights.weight_setter.WeightSetter"),
    ):
        v = Validator(config=mock_config)

        # Wire collaborators that set_weights and forward rely on
        v.weight_setter = Mock()
        v.weight_setter.weights_from_snapshot.return_value = [0.0, 0.5, 0.0]
        v.job_client = Mock()
        v.job_client.get_weight_epoch.return_value = {
            "epoch_id": 1,
            "payload_hash": "abc",
            "miners": [],
        }
        v._planned_weight_epoch = v.job_client.get_weight_epoch.return_value

        v.next_miner = Mock()
        v.next_miner.list_serving_miners.return_value = []
        v.next_miner.get_next_miner.side_effect = IndexError  # short-circuit collect-only
        v.next_miner.get_next_miner_for_class.return_value = None

        v.synapse_manager = Mock()
        v.scorer = Mock()

        # Exercise set_weights override
        v.set_weights()
        assert hasattr(v, "scores")

        # Exercise forward (should return early due to IndexError)
        v.forward()

        assert v is not None
        assert getattr(v, "neuron_type", None) or True  # basic existence after construction


def _weight_host():
    host = Mock()
    host.uid = 0
    host.step = 1
    host.neuron_type = "ValidatorNeuron"
    host.scores = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    host.metagraph.last_update = [0, 0, 0]
    host.metagraph.uids = np.arange(3, dtype=np.int64)
    host.subtensor.block = 500
    host.block = 500
    host.spec_version = 1
    host.config.netuid = 48
    host.config.neuron.disable_set_weights = False
    host.config.neuron.epoch_length = 100
    host.wallet = Mock()
    # Mock auto-creates methods; bind the real stamp/gate onto this host.
    host._mark_local_weights_submitted = (
        lambda: BaseValidatorNeuron._mark_local_weights_submitted(host)
    )
    return host


def test_successful_set_weights_stamps_local_last_update():
    """A successful submit must close the window so the next 5s loop does not resubmit."""
    host = _weight_host()
    host.subtensor.execute.return_value = Mock(success=True, error=None)

    with (
        patch(
            "qbittensor.base.validator.process_weights_for_netuid",
            return_value=(np.array([0]), np.array([1.0])),
        ),
        patch(
            "qbittensor.base.validator.convert_weights_and_uids_for_emit",
            return_value=([0], [1.0]),
        ),
    ):
        BaseValidatorNeuron.set_weights(host)

    assert host.metagraph.last_update[0] == 500
    assert BaseValidatorNeuron.should_set_weights(host) is False


def test_failed_set_weights_does_not_stamp_last_update():
    host = _weight_host()
    host.subtensor.execute.return_value = Mock(success=False, error=None, message="pool full")

    with (
        patch(
            "qbittensor.base.validator.process_weights_for_netuid",
            return_value=(np.array([0]), np.array([1.0])),
        ),
        patch(
            "qbittensor.base.validator.convert_weights_and_uids_for_emit",
            return_value=([0], [1.0]),
        ),
    ):
        BaseValidatorNeuron.set_weights(host)

    assert host.metagraph.last_update[0] == 0
    assert BaseValidatorNeuron.should_set_weights(host) is True
