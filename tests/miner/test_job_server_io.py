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

from qbittensor.miner.runtime.io import job_server as js
from qbittensor.miner.providers.base import AvailabilityStatus, Capabilities
from qbittensor.miner.providers.base import MinerIdentity


class DummyRegistry:
    def __init__(self):
        class RM:
            def __init__(self):
                class KP:
                    ss58_address = "5DummyHotkey11111111111111111111111111111111"
                self._keypair = KP()
                self.last = None

            def patch(self, endpoint: str, json: dict, params: dict = {}):
                self.last = {"endpoint": endpoint, "json": json, "params": params}

                class Resp:
                    status_code = 200
                return Resp()

        self._request_manager = RM()

        class FakeJobClient:
            def __init__(self, rm):
                self._rm = rm

            def patch_backend(self, payload):
                self._rm.patch("backends", payload)

            def patch_execution_status(self, execution_id, status, message=None):
                self._rm.patch(f"executions/{execution_id}", {"status": status, "message": message})
        self._job_client = FakeJobClient(self._request_manager)


def test_build_availability_fields():
    a = AvailabilityStatus(availability="ONLINE", is_available=True)
    ok, depth = js._build_availability_fields(a, pending_count=0, provider_queue=None)
    assert ok is True
    assert isinstance(depth, int)


def test_send_status_low_credits_not_accepting():
    reg = DummyRegistry()

    class Adapter:
        def get_accepting_jobs_override(self):
            return False

    reg.adapter = Adapter()
    identity = MinerIdentity(device_id="d1", provider="openquantum", vendor=None, device_type="QPU")
    availability = AvailabilityStatus(availability="ONLINE", is_available=False, status_msg="low_credits")
    status_data = {
        "identity": identity,
        "availability": availability,
        "capabilities": Capabilities(num_qubits=8, basis_gates=["x"], extras=None),
        "_pending_count": 0,
        "_inflight_count": 0,
    }
    js.send_status_to_job_server(reg, status_data)
    assert reg._request_manager.last is None


def test_send_status_to_job_server_does_not_patch(monkeypatch):
    reg = DummyRegistry()
    identity = MinerIdentity(device_id="d1", provider="mock", vendor=None, device_type="SIMULATOR")
    availability = AvailabilityStatus(availability="ONLINE", is_available=True)
    caps = Capabilities(num_qubits=8, basis_gates=["x"], extras=None)
    status_data = {
        "identity": identity, "availability": availability, "capabilities": caps,
    }
    status_data["_pending_count"] = 0
    status_data["_inflight_count"] = 0
    js.send_status_to_job_server(reg, status_data)
    assert reg._request_manager.last is None


def test_send_error_to_job_server_does_not_patch(monkeypatch):
    reg = DummyRegistry()
    js.send_error_to_job_server(reg, {"execution_id": "E", "message": "boom"})
    assert reg._request_manager.last is None
