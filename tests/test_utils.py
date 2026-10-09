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

import bittensor as bt
from unittest.mock import MagicMock

from qbittensor.database.database_manager import DatabaseManager
from tests.miner.constants import VALIDATOR_TEST_DB_NAME


def get_mock_metagraph(num_axons: int = 5):
    """Return a lightweight mock metagraph for unit tests (bittensor SDK v11)."""
    # Avoid MagicMock(spec=bt.Metagraph) — v11 Metagraph surface differs from template usage.
    mg = MagicMock()
    hotkeys = [f"hk{i}" for i in range(num_axons)]
    axons = []
    for i, hk in enumerate(hotkeys):
        # Real AxonInfo so BasicMiner pydantic validation accepts it
        axon = bt.AxonInfo(
            version=4,
            ip="127.0.0.1",
            port=8091 + i,
            ip_type=4,
            hotkey=hk,
            coldkey=f"ck{i}",
        )
        axons.append(axon)

    mg.hotkeys = hotkeys
    mg.axons = axons
    mg.n = num_axons
    mg.uids = list(range(num_axons))
    # Provide common attributes used by validators / weights / api code
    import numpy as np
    mg.S = np.ones(num_axons, dtype=float)
    # Default: no validator permits so NextMiner treats everyone as a miner
    mg.validator_permit = [False] * num_axons
    mg.validator_trust = np.full(num_axons, 0.5, dtype=float)
    mg.last_update = {i: 0 for i in range(num_axons)}
    mg.netuid = 2
    mg.sync = MagicMock()
    return mg


def get_mock_keypair():
    """Return a mock keypair instance for testing (v11 wallet Keypair)."""
    mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    keypair = bt.Keypair.create_from_mnemonic(mnemonic)
    return keypair


def get_mock_dendrite(keypair):
    """Build and return a mock dendrite based on a keypair."""
    # Dendrite expects a wallet-like object with .hotkey; keypair can stand in via SimpleNamespace.
    from types import SimpleNamespace
    wallet = SimpleNamespace(hotkey=keypair)
    return bt.Dendrite(wallet=wallet)


def clean_up_validator_db():
    db_manager = DatabaseManager(VALIDATOR_TEST_DB_NAME)
    db_manager.query_and_commit("DELETE FROM last_circuit")
    db_manager.query_and_commit("DELETE FROM active_miners")
    db_manager.query_and_commit("DELETE FROM execution_metrics")
