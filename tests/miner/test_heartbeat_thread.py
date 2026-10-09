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
from tests.test_utils import get_mock_keypair


@pytest.fixture
def tmp_db():
    db_name = "test_heartbeat_thread"
    db = DatabaseManager(db_name)
    # migrations applied on construction
    return db


def test_provider_thread_periodic_updates(monkeypatch, tmp_db):
    monkeypatch.setenv("JOB_SERVER_URL", "http://127.0.0.1:9999")
    keypair = get_mock_keypair()
    from unittest.mock import Mock
    from qbittensor.utils.services.job import JobClient
    jc = Mock(spec=JobClient)
    jc.request_upload_slot.return_value = {"upload_url": "http://ex", "id": "u1"}
    jr = JobRegistry(tmp_db, keypair, poll_interval_s=0.02, job_client=jc)

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
