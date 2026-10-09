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

from qbittensor.miner.runtime.threads.provider_thread import poll_once


def test_integration_registry_flow_end_to_end(registry, http_mock):
    # Submit -> poll -> complete -> persisted -> removed from tracking
    exec_id = "INT-1"
    registry.submit(
        exec_id,
        input_data_url="http://qasm",
        validator_hotkey="vhk",
        backend_class_id="test-class",
    )
    # Progress provider state until completed and clean-up
    for _ in range(300):
        poll_once(registry)
        with registry._lock:
            if exec_id not in registry._jobs:
                break
        time.sleep(0.01)
    assert not registry.is_tracking(exec_id)
    # Row is completed in DB
    rows = registry.db.query_with_values(
        "SELECT status, upload_data_id FROM executions WHERE execution_id = ?",
        (exec_id,),
    )
    assert rows and rows[0][0] == "Completed"
    assert rows[0][1] is not None
