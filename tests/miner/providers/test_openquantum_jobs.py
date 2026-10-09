# The MIT License (MIT)
# Copyright © 2026 qBitTensor Labs

from qbittensor.miner.providers.openquantum.config import OpenQuantumConfig, PRIVATE_PLAN_ID
from qbittensor.miner.providers.openquantum.jobs import JobService, _map_status


def _cfg() -> OpenQuantumConfig:
    return OpenQuantumConfig(
        access_token="tok",
        organization_id="org-1",
        scheduler_url="http://scheduler.test",
        management_url="http://management.test",
        dry_run=False,
        min_credits=100.0,
        queue_priority_id="prio",
        execution_plan_id=PRIVATE_PLAN_ID,
        subcategory_id="oth:oth",
        http_timeout_s=5,
    )


def test_map_status_mirrors_platform_job():
    assert _map_status("Pending") == "QUEUED"
    assert _map_status("Queued") == "QUEUED"
    assert _map_status("Running") == "RUNNING"
    assert _map_status("Completed") == "COMPLETED"
    assert _map_status("Failed") == "FAILED"
    assert _map_status("Canceled") == "CANCELLED"


def test_submit_private_job_http(monkeypatch):
    svc = JobService(_cfg())
    calls = []

    class Resp:
        def __init__(self, payload, status=200):
            self._payload = payload
            self.status_code = status
            self.content = b"{}" if payload is not None else b""

        def raise_for_status(self):
            if self.status_code >= 400:
                import requests
                err = requests.HTTPError()
                err.response = self
                raise err

        def json(self):
            return self._payload

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs.get("json")))
        if url.endswith("v1/jobs/upload"):
            return Resp({"id": "up-1", "url": "http://s3/put"})
        if url.endswith("v1/jobs/prepare"):
            return Resp({"id": "prep-1"})
        if url.endswith("v1/jobs/prepare/prep-1"):
            return Resp({
                "status": "Completed",
                "quote": [{
                    "execution_plan_id": PRIVATE_PLAN_ID,
                    "price": 12.5,
                    "queue_priorities": [{"queue_priority_id": "prio-std"}],
                }],
            })
        if url.endswith("v1/jobs") and method == "POST":
            return Resp({"id": "job-9", "status": "Pending"})
        return Resp({})

    monkeypatch.setattr(svc._session, "request", fake_request)

    class PutResp:
        status_code = 200

        def raise_for_status(self):
            return None

    monkeypatch.setattr(svc._session, "put", lambda *a, **k: PutResp())
    job_id = svc.submit(
        "OPENQASM 2.0;",
        "ionq:aria-1",
        999,
        dry_run=False,
        configuration_data={"shots": 100, "n": 2},
    )
    assert job_id == "job-9"
    create = [c for c in calls if c[0] == "POST" and c[1].endswith("v1/jobs")][0]
    assert create[2]["execution_plan_id"] == PRIVATE_PLAN_ID
    assert svc.last_private_price() == 12.5
    prep = [c for c in calls if c[0] == "POST" and c[1].endswith("v1/jobs/prepare")][0]
    assert prep[2]["backend_class_id"] == "ionq:aria-1"
    assert prep[2]["configuration_data"] == {"shots": 100, "n": 2}
    assert "shots" not in prep[2]
    svc.submit(
        "OPENQASM 2.0;",
        "ionq:aria-1",
        50,
        dry_run=False,
        configuration_data={"n": 2},
    )
    bare = [c for c in calls if c[0] == "POST" and c[1].endswith("v1/jobs/prepare")][-1]
    assert bare[2]["configuration_data"] == {"n": 2}


def test_poll_returns_filtered_job_message(monkeypatch):
    svc = JobService(_cfg())
    monkeypatch.setattr(
        svc,
        "_get_job",
        lambda job_id: {
            "status": "Failed",
            "message": "Number of qubits exceeds the device",
        },
    )
    status, remaining, message = svc.poll("job-9", dry_run=False)
    assert status == "FAILED"
    assert remaining == 0
    assert message == "Number of qubits exceeds the device"


def test_poll_dry_run_has_no_message():
    svc = JobService(_cfg())
    job_id = svc.submit("OPENQASM 2.0;", "ionq:aria-1", 10, dry_run=True)
    status, _remaining, message = svc.poll(job_id, dry_run=True)
    assert status in ("QUEUED", "RUNNING", "COMPLETED")
    assert message is None


def test_receipt_waits_for_private_job_proof(monkeypatch):
    svc = JobService(_cfg())
    payloads = [
        {"status": "Completed", "output_data_url": None, "proof": None},
        {
            "status": "Completed",
            "output_data_url": None,
            "execution_plan_id": PRIVATE_PLAN_ID,
            "proof": {
                "statement": "pot.job.v1\njob_id=job-9",
                "signature": "sig",
                "certificate_serial": "ab",
            },
        },
    ]

    def fake_get(job_id):
        return payloads.pop(0) if payloads else payloads[-1:] or {}

    monkeypatch.setattr(svc, "_get_job", fake_get)
    monkeypatch.setattr("qbittensor.miner.providers.openquantum.jobs.time.sleep", lambda *_: None)
    receipt = svc.receipt("job-9", "ionq:aria-1", dry_run=False, shots=100)
    assert receipt.metadata["proof"]["signature"] == "sig"
    assert payloads == []
