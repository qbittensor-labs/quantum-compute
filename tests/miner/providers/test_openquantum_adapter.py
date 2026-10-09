# The MIT License (MIT)
# Copyright © 2026 qBitTensor Labs

from qbittensor.miner.providers.openquantum.adapter import OpenQuantumAdapter
from qbittensor.miner.providers.openquantum.config import OpenQuantumConfig
from qbittensor.miner.providers.registry import get_adapter


def _dry_cfg() -> OpenQuantumConfig:
    return OpenQuantumConfig(
        access_token=None,
        organization_id=None,
        scheduler_url="http://scheduler",
        management_url="http://management",
        dry_run=True,
        min_credits=100.0,
        queue_priority_id="prio",
        execution_plan_id="plan",
        subcategory_id="oth:oth",
        http_timeout_s=5,
    )


def test_registry_resolves_openquantum(monkeypatch):
    monkeypatch.setenv("OPENQUANTUM_DRY_RUN", "1")
    adapter = get_adapter("openquantum")
    assert isinstance(adapter, OpenQuantumAdapter)


def test_dry_run_submit_poll_receipt():
    adapter = OpenQuantumAdapter(config=_dry_cfg())
    devices = adapter.list_devices()
    assert devices[0].device_id == "openquantum"
    handle = adapter.submit("OPENQASM 2.0; // test", device_id="ionq:aria-1", shots=10)
    status = adapter.poll(handle)
    assert status.status in ("QUEUED", "RUNNING", "COMPLETED")
    assert status.message is None
    receipt = adapter.get_job_receipt(handle)
    assert receipt.provider == "openquantum"
    assert receipt.metadata.get("execution_plan_id")


def test_low_credits_not_accepting(monkeypatch):
    adapter = OpenQuantumAdapter(config=_dry_cfg())
    monkeypatch.setattr(
        "qbittensor.miner.providers.openquantum.adapter.should_rate_limit_for_low_credits",
        lambda cfg: True,
    )
    monkeypatch.setattr(
        "qbittensor.miner.providers.openquantum.adapter.get_remaining_credits",
        lambda cfg: 10.0,
    )
    avail = adapter.get_availability()
    assert avail is not None
    assert avail.is_available is False
    assert adapter.get_accepting_jobs_override() is False
    assert adapter.should_rate_limit_request(shots=100) is True


def test_list_public_classes_prefers_env(monkeypatch):
    monkeypatch.setenv("PUBLIC_BACKEND_CLASSES", "ionq:forte-1,quantumrings:qasm3")
    adapter = OpenQuantumAdapter(config=_dry_cfg())
    assert adapter.list_public_classes() == ["ionq:forte-1", "quantumrings:qasm3"]


def test_list_public_classes_empty_when_unset(monkeypatch):
    monkeypatch.delenv("PUBLIC_BACKEND_CLASSES", raising=False)
    adapter = OpenQuantumAdapter(config=_dry_cfg())
    assert adapter.list_public_classes() == []


def test_from_env_does_not_require_backend_class(monkeypatch):
    monkeypatch.setattr(
        "qbittensor.miner.providers.openquantum.config.load_env",
        lambda: None,
    )
    for key in (
        "OPENQUANTUM_BACKEND_CLASS",
        "OPENQUANTUM_ACCESS_TOKEN",
        "PUBLIC_BACKEND_CLASSES",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENQUANTUM_DRY_RUN", "0")
    monkeypatch.setenv("OPENQUANTUM_CLIENT_ID", "id")
    monkeypatch.setenv("OPENQUANTUM_CLIENT_SECRET", "secret")
    monkeypatch.setenv("OPENQUANTUM_ORGANIZATION_ID", "org")
    cfg = OpenQuantumConfig.from_env(strict=True)
    assert cfg.organization_id == "org"
    assert cfg.client_id == "id"
    assert "backend_class" not in cfg.model_fields


def test_submit_requires_explicit_backend_class():
    adapter = OpenQuantumAdapter(config=_dry_cfg())
    try:
        adapter.submit("OPENQASM 2.0;", shots=1)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "backend class is required" in str(e)


def test_submit_blocked_when_low_credits(monkeypatch):
    cfg = _dry_cfg()
    cfg.dry_run = False
    cfg.access_token = "tok"
    cfg.organization_id = "org"
    adapter = OpenQuantumAdapter(config=cfg)
    monkeypatch.setattr(adapter, "should_rate_limit", lambda: True)
    try:
        adapter.submit("OPENQASM 2.0;", device_id="ionq:aria-1", shots=1)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "MIN_CREDITS" in str(e)
