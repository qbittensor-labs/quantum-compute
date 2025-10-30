import bittensor as bt

from pkg.database.database_manager import DatabaseManager
from tests.miner.constants import VALIDATOR_TEST_DB_NAME


def get_mock_metagraph(num_axons: int) -> bt.Metagraph:
    """Return a mock bt.Metagraph instance for testing"""
    netuid = 2
    network = "test" 
    lite = True
    sync = False
    metagraph = bt.metagraph(netuid, network, lite, sync)
    metagraph.axons = []
    hotkeys = []
    for i in range(num_axons):
        axon = bt.axon()
        # Set hotkey attribute for the axon
        axon.hotkey = f"hk{i}"
        metagraph.axons.append(axon)
        hotkeys.append(f"hk{i}")
    
    # Use setattr to set the private attribute that hotkeys property uses
    # In bittensor, hotkeys property typically derives from axons
    # We'll mock it by overriding the property directly
    type(metagraph).hotkeys = property(lambda self: hotkeys)
    return metagraph

def get_mock_keypair() -> bt.Keypair:
    """Return a mock bt.Keypair instance for testing"""
    mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    keypair = bt.Keypair.create_from_mnemonic(mnemonic)
    return keypair

def get_mock_dendrite(keypair: bt.Keypair) -> bt.Dendrite:
    """Build and return a mock dendrite based on a keypair"""
    return bt.dendrite(keypair)

def clean_up_validator_db():
    db_manager = DatabaseManager(VALIDATOR_TEST_DB_NAME)
    db_manager.query_and_commit("DELETE FROM last_circuit")
    db_manager.query_and_commit("DELETE FROM active_miners")
    db_manager.query_and_commit("DELETE FROM execution_metrics")
