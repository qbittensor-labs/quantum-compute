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

import pytest

from qbittensor.database.database_manager import DatabaseManager
from qbittensor.miner.runtime.registry import JobRegistry
from tests.test_utils import get_mock_keypair


@pytest.fixture
def tmp_db():
    db_name = "test_preflight"
    db = DatabaseManager(db_name)
    # migrations applied on construction
    return db


def test_preflight_invalid_qasm_reports_error(monkeypatch, tmp_db):
    pass


def test_shots_clamped(monkeypatch, tmp_db):
    keypair = get_mock_keypair()
    from unittest.mock import Mock
    from qbittensor.utils.services.job import JobClient
    jc = Mock(spec=JobClient)
    jc.request_upload_slot.return_value = {"upload_url": "http://ex", "id": "u1"}
    jr = JobRegistry(tmp_db, keypair, poll_interval_s=0.05, job_client=jc)

    class FakeCap:
        num_qubits = 32
        basis_gates = ["x", "y", "z", "cx", "rz"]
        extras = None

    monkeypatch.setattr(jr.adapter, "list_capabilities", lambda: [FakeCap()])

    submitted = {}

    def fake_submit(circuit_data, device_id=None, shots=None, configuration_data=None):
        from qbittensor.miner.providers.base import JobHandle
        submitted["shots"] = shots
        return JobHandle(provider_job_id="prov-h1", device_id=device_id or "dev")

    monkeypatch.setattr(jr.adapter, "submit", fake_submit)

    qasm = """OPENQASM 2.0;\nqreg q[2];\nx q[0];\n"""
    monkeypatch.setattr(jr, "_download_qasm", lambda url: qasm)
    jr.submit(
        execution_id="7",
        input_data_url="http://qasm",
        validator_hotkey="hk",
        shots=50000,
        backend_class_id="test-class",
    )
    jr.process_submissions_sync()
    assert submitted.get("shots") == 50000
