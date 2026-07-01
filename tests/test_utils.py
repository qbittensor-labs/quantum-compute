import bittensor as bt
from unittest.mock import MagicMock

from pkg.database.database_manager import DatabaseManager
from tests.miner.constants import VALIDATOR_TEST_DB_NAME


def get_mock_metagraph(num_axons: int = 5) -> "bt.Metagraph":
    """Return a lightweight mock bt.Metagraph for unit tests (works with bittensor v10+)."""
    mg = MagicMock(spec=bt.Metagraph)
    hotkeys = [f"hk{i}" for i in range(num_axons)]
    axons = []
    for i, hk in enumerate(hotkeys):
        axon = MagicMock()
        axon.hotkey = hk
        axon.ip = "127.0.0.1"
        axon.port = 8091 + i
        axons.append(axon)

    mg.hotkeys = hotkeys
    mg.axons = axons
    mg.n = num_axons
    mg.uids = list(range(num_axons))
    # Provide common attributes used by validators / weights / api code
    import numpy as np
    mg.S = np.ones(num_axons, dtype=float)
    mg.validator_trust = np.full(num_axons, 0.5, dtype=float)
    mg.last_update = {i: 0 for i in range(num_axons)}
    mg.netuid = 2
    mg.sync = MagicMock()
    return mg

def get_mock_keypair() -> bt.Keypair:
    """Return a mock bt.Keypair instance for testing"""
    mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    keypair = bt.Keypair.create_from_mnemonic(mnemonic)
    return keypair

def get_mock_dendrite(keypair: bt.Keypair) -> bt.Dendrite:
    """Build and return a mock dendrite based on a keypair"""
    return bt.Dendrite(wallet=keypair)

def clean_up_validator_db():
    db_manager = DatabaseManager(VALIDATOR_TEST_DB_NAME)
    db_manager.query_and_commit("DELETE FROM last_circuit")
    db_manager.query_and_commit("DELETE FROM active_miners")
    db_manager.query_and_commit("DELETE FROM execution_metrics")
