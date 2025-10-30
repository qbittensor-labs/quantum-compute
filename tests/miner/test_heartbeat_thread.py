import time
import pytest

from pkg.database.database_manager import DatabaseManager
from qbittensor.miner.miner_table_initializer import MinerTableInitializer
from qbittensor.miner.runtime.registry import JobRegistry
from tests.test_utils import get_mock_keypair


@pytest.fixture
def tmp_db():
    db_name = "test_heartbeat_thread"
    db = DatabaseManager(db_name)
    MinerTableInitializer(db).create_tables()
    return db


def test_provider_thread_periodic_updates(monkeypatch, tmp_db):
    monkeypatch.setenv("JOB_SERVER_URL", "http://127.0.0.1:9999")
    keypair = get_mock_keypair()
    jr = JobRegistry(tmp_db, keypair, poll_interval_s=0.02)

    status_calls = {"n": 0}

    def fake_collect_status(_registry):
        status_calls["n"] += 1

    import qbittensor.miner.runtime.threads.status_thread as status_thread
    monkeypatch.setattr(status_thread, "collect_status_data", fake_collect_status)
    
    jr._last_status_update = 0

    jr.start()
    time.sleep(0.6)
    jr.stop()

    assert status_calls["n"] >= 1


