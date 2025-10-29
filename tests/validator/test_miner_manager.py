import bittensor as bt
from typing import List
import pytest

from pkg.database.database_manager import DatabaseManager
from qbittensor.utils.timestamping import timestamp
from qbittensor.validator.miner_manager.MinerManager import Miner, MinerManager
from tests.miner.constants import VALIDATOR_TEST_DB_NAME
from tests.test_utils import get_mock_metagraph
from tests.validator.utils import cleanup_db, setup_db

# Verified Miners
m1 = Miner(uid=0, hotkey="M1")
m2 = Miner(uid=1, hotkey="M2")
m3 = Miner(uid=2, hotkey="M3")

# Unverified Miners
m4 = Miner(uid=3, hotkey="M4")
m5 = Miner(uid=4, hotkey="M5")
m6 = Miner(uid=5, hotkey="M6")
m7 = Miner(uid=6, hotkey="M7")

verified_miners: List[Miner] = [m1, m2, m3]
unverified_miners: List[Miner] = [m4, m5, m6, m7]
all_miners: List[Miner] = verified_miners + unverified_miners

# --------------------------
# Fixtures
# --------------------------
@pytest.fixture
def setup() -> MinerManager:
    """Runs before each test."""
    db_manager = setup_db()
    metagraph: bt.Metagraph = get_mock_metagraph(num_axons=len(all_miners))
    return MinerManager(db_manager, metagraph)


@pytest.fixture(scope="session", autouse=True)
def teardown():
    """Runs once after all tests in this session."""
    yield  # tests run here
    # cleanup logic after all tests
    db_manager = DatabaseManager(VALIDATOR_TEST_DB_NAME)
    cleanup_db(db_manager)


# --------------------------
# Tests for MinerManager
# --------------------------

def test_get_active_miners_from_db(setup) -> None:
    mm = setup
    query = """
        INSERT OR IGNORE INTO active_miners
        (hotkey, uid, timestamp)
        VALUES (?, ?, ?)
    """
    now = timestamp()
    values = [(x.hotkey, x.uid, now) for x in all_miners]
    mm.database_manager.query_and_commit_many(query, values)

    tracked_miners: List[Miner] = mm._get_active_miners_from_db()

    # Test that all miners were found
    assert len(tracked_miners) == len(all_miners)

    # Test that all miners match
    for miner in all_miners:
        assert miner in tracked_miners

def test_get_new_miners(setup) -> None:
    mm = setup

    # m7 is a new miner
    metagraph_miners = set([m1, m2, m3, m4, m5, m6, m7])
    db_miners = set([m1, m2, m3, m4, m5, m6])

    new_miners = mm._get_new_miners(metagraph_miners, db_miners)
    assert len(new_miners) == 1
    assert m7 in new_miners

def test_get_deregistered_miners(setup) -> None:
    mm = setup

    # m7 is a deregistered miner
    metagraph_miners = set([m1, m2, m3, m4, m5, m6])
    db_miners = set([m1, m2, m3, m4, m5, m6, m7])

    deregistered_miners = mm._get_deregistered_miners(metagraph_miners, db_miners)
    assert len(deregistered_miners) == 1
    assert m7 in deregistered_miners

def test_track_new_miners(setup) -> None:
    mm = setup

    # m7 is a new miner
    metagraph_miners = set([m1, m2, m3, m4, m5, m6, m7])
    db_miners = set([m1, m2, m3, m4, m5, m6])

    mm._track_new_miners(metagraph_miners, db_miners)
    query = """
        SELECT uid
        FROM active_miners
        WHERE hotkey=?
    """
    values = (m7.hotkey,)
    results = mm.database_manager.query_with_values(query, values)
    
    # Test that there is a result
    assert len(results) == 1
    
    miner = results[0]
    # Test that the uid matches the new miner (m7)
    assert miner[0] == m7.uid

def test_run(setup) -> None:
    mm = setup
    now = timestamp()

    # Populate last_circuit table
    query = """INSERT OR IGNORE INTO last_circuit (miner_hotkey, timestamp) VALUES (?, ?)"""
    values = [(x.hotkey, now) for x in all_miners]
    mm.database_manager.query_and_commit_many(query, values)

    # Populate active_miners table (same values as above)
    query = """INSERT OR IGNORE INTO active_miners (hotkey, uid, timestamp) VALUES (?, ?, ?)"""
    values = [(x.hotkey, x.uid, now) for x in all_miners]
    mm.database_manager.query_and_commit_many(query, values)

    # m7 was deregistered
    metagraph_miners = set([m1, m2, m3, m4, m5, m6])

    mm._run(metagraph_miners)

    hotkeys_result = mm.database_manager.query("SELECT miner_hotkey FROM last_circuit")
    hotkeys = [result[0] for result in hotkeys_result]

    # Test m7 data is gone
    assert m7.hotkey not in hotkeys

    last_circuit_result = mm.database_manager.query("SELECT miner_hotkey FROM last_circuit")

    # Test length of results
    assert len(last_circuit_result) == 6
    hotkeys = [result[0] for result in last_circuit_result]

    # Test m7 data is gone
    assert m7.hotkey not in hotkeys

    active_miners_result = mm.database_manager.query("SELECT hotkey FROM active_miners")

    # Test length of results
    assert len(active_miners_result) == 6
    hotkeys = [result[0] for result in active_miners_result]

    # Test m7 data is gone
    assert m7.hotkey not in hotkeys
