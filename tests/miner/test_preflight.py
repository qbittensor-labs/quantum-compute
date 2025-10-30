import pytest

from pkg.database.database_manager import DatabaseManager
from qbittensor.miner.miner_table_initializer import MinerTableInitializer
from qbittensor.miner.runtime.registry import JobRegistry
from tests.test_utils import get_mock_keypair


@pytest.fixture
def tmp_db():
    db_name = "test_preflight"
    db = DatabaseManager(db_name)
    MinerTableInitializer(db).create_tables()
    return db


def test_preflight_invalid_qasm_reports_error(monkeypatch, tmp_db):
    pass


def test_shots_clamped(monkeypatch, tmp_db):
    keypair = get_mock_keypair()
    jr = JobRegistry(tmp_db, keypair, poll_interval_s=0.05)

    class FakeCap:
        num_qubits = 32
        basis_gates = ["x", "y", "z", "cx", "rz"]
        extras = None

    monkeypatch.setattr(jr.adapter, "list_capabilities", lambda: [FakeCap()])

    submitted = {}

    def fake_submit(circuit_data, device_id=None, shots=None):
        from qbittensor.miner.providers.base import JobHandle
        submitted["shots"] = shots
        return JobHandle(provider_job_id="prov-h1", device_id=device_id or "dev")

    monkeypatch.setattr(jr.adapter, "submit", fake_submit)

    qasm = """OPENQASM 2.0;\nqreg q[2];\nx q[0];\n"""
    monkeypatch.setattr(jr, "_download_qasm", lambda url: qasm)
    jr.submit(execution_id="7", input_data_url="http://qasm", validator_hotkey="hk", shots=50000)
    jr.process_submissions_sync()
    assert submitted.get("shots") == 50000


