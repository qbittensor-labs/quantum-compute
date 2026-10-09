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

import time
import pytest

from qbittensor.database.database_manager import DatabaseManager
from qbittensor.miner.runtime.registry import JobRegistry
from qbittensor.miner.runtime.threads.provider_thread import poll_once
from tests.test_utils import get_mock_keypair


@pytest.fixture
def tmp_db():
    db_name = "miner_test_budget_cb"
    db = DatabaseManager(db_name)
    # migrations applied on construction
    return db


def _count_completed(db: DatabaseManager, execution_id: str) -> int:
    query = "SELECT COUNT(*) FROM executions WHERE execution_id=? AND status='Completed'"
    with db.lock:
        rows = db.query_with_values(query, (execution_id,))
    return rows[0][0] if rows else 0


def test_on_job_completed_completes_and_persists(tmp_db, monkeypatch, http_mock):
    keypair = get_mock_keypair()
    from unittest.mock import Mock
    from qbittensor.utils.services.job import JobClient
    jc = Mock(spec=JobClient)
    jc.request_upload_slot.return_value = {"upload_url": "http://ex", "id": "u1"}
    jr = JobRegistry(tmp_db, keypair, poll_interval_s=0.02, job_client=jc)

    execution_id = "91011"
    monkeypatch.setattr(jr, "_download_qasm", lambda url: "OPENQASM 2.0; // mock")
    jr.submit(
        execution_id=execution_id,
        input_data_url="http://qasm",
        validator_hotkey="hk",
        shots=10,
        backend_class_id="test-class",
    )

    jr.start()

    deadline = time.time() + 3.0
    while time.time() < deadline and _count_completed(tmp_db, execution_id) == 0:
        poll_once(jr)
        time.sleep(0.05)

    jr.stop()

    assert _count_completed(tmp_db, execution_id) == 1
