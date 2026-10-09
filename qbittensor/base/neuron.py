# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
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

import copy

import bittensor as bt

from abc import ABC, abstractmethod

# Sync calls set weights and also resyncs the metagraph.
from qbittensor import bt_compat  # noqa: F401
from qbittensor.bt_compat import MetagraphAdapter
from qbittensor.utils.config import check_config, add_args, config
from qbittensor.utils.misc import ttl_get_block
from qbittensor import __spec_version__ as spec_version
from qbittensor.mock import MockSubtensor, MockMetagraph


def _wallet_from_config(cfg):
    wallet_cfg = getattr(cfg, "wallet", None)
    name = getattr(wallet_cfg, "name", "default") if wallet_cfg else "default"
    hotkey = getattr(wallet_cfg, "hotkey", "default") if wallet_cfg else "default"
    path = getattr(wallet_cfg, "path", None) if wallet_cfg else None
    kwargs = {"name": name, "hotkey": hotkey}
    if path:
        kwargs["path"] = path
    # Use bt.Wallet so unit tests can patch qbittensor.base.neuron.bt.Wallet.
    return bt.Wallet(**kwargs)


def _network_from_config(cfg) -> str:
    st = getattr(cfg, "subtensor", None)
    endpoint = getattr(st, "chain_endpoint", None) if st else None
    network = getattr(st, "network", None) if st else None
    # Prefer explicit ws(s) endpoint when provided.
    if endpoint and str(endpoint).startswith(("ws://", "wss://")):
        return str(endpoint)
    return str(network or "finney")


def _fetch_metagraph(subtensor, *, netuid: int) -> MetagraphAdapter:
    """Fetch a metagraph snapshot via ``subtensor.subnets.metagraph``."""
    mg = subtensor.subnets.metagraph(netuid=netuid)
    if isinstance(mg, MetagraphAdapter):
        return mg
    return MetagraphAdapter(mg, netuid=netuid, subtensor=subtensor)


def _is_hotkey_registered(subtensor: bt.Subtensor, *, netuid: int, hotkey_ss58: str) -> bool:
    """Registration is checked via ``subtensor.neurons.uid`` (None if not registered)."""
    return subtensor.neurons.uid(hotkey_ss58=hotkey_ss58, netuid=netuid) is not None


def _endpoint_label(subtensor, config=None) -> str:
    """Human-readable network/endpoint for logs."""
    for src in (subtensor, getattr(config, "subtensor", None) if config is not None else None):
        if src is None:
            continue
        label = getattr(src, "endpoint", None) or getattr(src, "network", None)
        if label:
            return str(label)
    return "?"


class BaseNeuron(ABC):
    """
    Base class for Bittensor miners. This class is abstract and should be inherited by a subclass. It contains the core logic for all neurons; validators and miners.

    In addition to creating a wallet, subtensor, and metagraph, this class also handles the synchronization of the network state via a basic checkpointing mechanism based on epoch length.
    """

    neuron_type: str = "BaseNeuron"

    @classmethod
    def check_config(cls, config: "bt.Config"):
        check_config(cls, config)

    @classmethod
    def add_args(cls, parser):
        add_args(cls, parser)

    @classmethod
    def config(cls):
        return config(cls)

    subtensor: "bt.Subtensor"
    wallet: "bt.Wallet"
    metagraph: "MetagraphAdapter"
    spec_version: int = spec_version

    @property
    def block(self):
        return ttl_get_block(self)

    def __init__(self, config=None):
        base_config = copy.deepcopy(config) if config is not None else None
        self.config = self.config()
        if base_config is not None:
            self.config = self.config.merge(base_config)
        self.check_config(self.config)

        # Set up logging with the provided configuration.
        bt.logging.set_config(config=self.config.logging)

        # If a gpu is required, set the device to cuda:N (e.g. cuda:0)
        self.device = self.config.neuron.device

        # Log the configuration for reference.
        bt.logging.info(self.config)

        # Build Bittensor objects
        # These are core Bittensor classes to interact with the network.
        bt.logging.info("Setting up bittensor objects.")

        # The wallet holds the cryptographic key pairs for the miner.
        if self.config.mock:
            self.wallet = bt.MockWallet(
                name=getattr(self.config.wallet, "name", "default"),
                hotkey=getattr(self.config.wallet, "hotkey", "default"),
            )
            self.subtensor = MockSubtensor(
                self.config.netuid, wallet=self.wallet
            )
            self.metagraph = MockMetagraph(
                self.config.netuid, subtensor=self.subtensor
            )
        else:
            self.wallet = _wallet_from_config(self.config)
            network = _network_from_config(self.config)
            self.subtensor = bt.Subtensor(network=network)
            self.metagraph = _fetch_metagraph(
                self.subtensor, netuid=self.config.netuid
            )

        bt.logging.info(f"Wallet: {self.wallet}")
        bt.logging.info(f"Subtensor: {self.subtensor}")
        bt.logging.info(f"Metagraph: {self.metagraph}")

        # Check if the miner is registered on the Bittensor network before proceeding further.
        self.check_registered()

        # Each miner gets a unique identity (UID) in the network for differentiation.
        self.uid = self.metagraph.hotkeys.index(
            self.wallet.hotkey.ss58_address
        )
        bt.logging.info(
            f"Running neuron on subnet: {self.config.netuid} with uid {self.uid} "
            f"using network: {_endpoint_label(self.subtensor, self.config)}"
        )
        self.step = 0

    @abstractmethod
    async def forward(self, synapse: bt.Synapse) -> bt.Synapse:
        ...

    @abstractmethod
    def run(self):
        ...

    def sync(self):
        """
        Wrapper for synchronizing the state of the network for the given miner or validator.
        """
        # Ensure miner or validator hotkey is still registered on the network.
        self.check_registered()

        if self.should_sync_metagraph():
            self.resync_metagraph()

        if self.should_set_weights():
            self.set_weights()

        # Always save state.
        self.save_state()

    def check_registered(self):
        # --- Check for registration.
        registered = _is_hotkey_registered(
            self.subtensor,
            netuid=self.config.netuid,
            hotkey_ss58=self.wallet.hotkey.ss58_address,
        )
        if not registered:
            bt.logging.error(
                f"Wallet: {self.wallet} is not registered on netuid {self.config.netuid}."
                f" Please register the hotkey using `btcli subnets register` before trying again"
            )
            exit()

    def should_sync_metagraph(self):
        """
        Check if enough epoch blocks have elapsed since the last checkpoint to sync.
        """
        return (
            self.block - self.metagraph.last_update[self.uid]
        ) > self.config.neuron.epoch_length

    def should_set_weights(self) -> bool:
        # Don't set weights on initialization.
        if self.step == 0:
            return False

        # Miners never set weights; validator configs expose disable_set_weights.
        if self.neuron_type == "MinerNeuron":
            return False
        if getattr(self.config.neuron, "disable_set_weights", False):
            return False

        # Define appropriate logic for when set weights.
        return (
            (self.block - self.metagraph.last_update[self.uid])
            > self.config.neuron.epoch_length
        )

    def save_state(self):
        bt.logging.trace(
            "save_state() not implemented for this neuron. You can implement this function to save model checkpoints or other useful data."
        )

    def load_state(self):
        bt.logging.trace(
            "load_state() not implemented for this neuron. You can implement this function to load model checkpoints or other useful data."
        )
