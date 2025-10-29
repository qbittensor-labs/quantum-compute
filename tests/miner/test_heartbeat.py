import pytest

from pkg.database.database_manager import DatabaseManager
from qbittensor.miner.miner_table_initializer import MinerTableInitializer
from qbittensor.miner.runtime.registry import JobRegistry
from qbittensor.miner.providers.base import AvailabilityStatus
from tests.test_utils import get_mock_keypair


@pytest.fixture
def tmp_db():
    db_name = "test_heartbeat"
    db = DatabaseManager(db_name)
    MinerTableInitializer(db).create_tables()
    return db


def test_status_update_payload(monkeypatch, tmp_db):
    monkeypatch.setenv("JOB_SERVER_URL", "http://127.0.0.1:9999")
    keypair = get_mock_keypair()
    jr = JobRegistry(tmp_db, keypair, poll_interval_s=0.05)

    class FakeCap:
        num_qubits = 4
        basis_gates = ["x", "cx"]
        extras = {"vendor": "mock"}

    monkeypatch.setattr(jr.adapter, "list_capabilities", lambda: [FakeCap()])
    monkeypatch.setattr(
        jr.adapter,
        "get_availability",
        lambda device_id: AvailabilityStatus(
            availability="ONLINE",
            pending_jobs=0,
            is_available=True,
            next_available=None,
            status_msg="ok",
        ),
    )

    captured = {}

    def fake_patch(url, json=None, headers=None, params=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        class Resp:
            status_code = 200
        return Resp()

    monkeypatch.setattr("requests.sessions.Session.patch", lambda self, url, *a, **k: fake_patch(url, *a, **k))

    from qbittensor.miner.runtime.io.job_server import send_status_to_job_server
    jr._collect_status_data()
    try:
        status_data = jr._status_queue.get_nowait()
    except Exception:
        status_data = {"identity": None, "availability": None, "capabilities": None, "pricing": None}
    send_status_to_job_server(jr, status_data)

    assert captured.get("url", "").endswith("/backends")
    body = captured.get("json", {})
    for key in ("accepting_jobs", "status", "queue_depth", "metadata", "pricing"):
        assert key in body


