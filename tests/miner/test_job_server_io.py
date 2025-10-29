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


def test_build_availability_fields():
    a = AvailabilityStatus(availability="ONLINE", is_available=True)
    ok, depth = js._build_availability_fields(a, pending_count=0, provider_queue=None)
    assert ok is True
    assert isinstance(depth, int)


def test_build_pricing_fields_snake_and_camel():
    snake = js._build_pricing_fields({"per_task": 1, "per_shot": 2, "per_minute": 3})
    assert snake == {"per_task": 1, "per_shot": 2, "per_minute": 3}
    camel = js._build_pricing_fields({"perTask": 1, "perShot": 2, "perMinute": 3})
    assert camel == {"per_task": 1, "per_shot": 2, "per_minute": 3}


def test_send_status_to_job_server_sends_patch(monkeypatch):
    reg = DummyRegistry()
    identity = MinerIdentity(device_id="d1", provider="mock", vendor=None, device_type="SIMULATOR")
    availability = AvailabilityStatus(availability="ONLINE", is_available=True)
    caps = Capabilities(num_qubits=8, basis_gates=["x"], extras=None)
    status_data = {
        "identity": identity, "availability": availability, "capabilities": caps, "pricing": {"perTask": 0.01}
    }
    # include pending counts for API
    status_data["_pending_count"] = 0
    status_data["_inflight_count"] = 0
    js.send_status_to_job_server(reg, status_data)
    sent = reg._request_manager.last
    assert sent and sent.get("endpoint") == "backends"
    assert sent["json"]["pricing"]["per_task"] == 0.01


def test_send_error_to_job_server_patches_execution(monkeypatch):
    reg = DummyRegistry()
    js.send_error_to_job_server(reg, {"execution_id": "E", "message": "boom"})
    sent = reg._request_manager.last
    assert sent["endpoint"].startswith("executions/") or sent["endpoint"].startswith("execution/")
    assert sent["json"]["status"] == "Failed"


