# The MIT License (MIT)
# Copyright © 2026 qBitTensor Labs

from qbittensor.miner.providers.openquantum.config import OpenQuantumConfig
from qbittensor.miner.providers.openquantum.credits import (
    below_min_credits,
    get_remaining_credits,
    should_rate_limit_for_low_credits,
)


def _cfg(**kwargs) -> OpenQuantumConfig:
    base = dict(
        access_token="tok",
        organization_id="org-1",
        scheduler_url="http://scheduler",
        management_url="http://management",
        dry_run=False,
        min_credits=100.0,
        queue_priority_id="prio",
        execution_plan_id="plan",
        subcategory_id="oth:oth",
        http_timeout_s=5,
    )
    base.update(kwargs)
    return OpenQuantumConfig(**base)


def test_get_remaining_credits_uses_full_credits(monkeypatch):
    import qbittensor.miner.providers.openquantum.credits as credits

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"spark_credits": 5.0, "full_credits": 250.5}

    monkeypatch.setattr(credits.requests, "get", lambda *a, **k: Resp())
    assert get_remaining_credits(_cfg()) == 250.5


def test_below_min_credits(monkeypatch):
    monkeypatch.setattr(
        "qbittensor.miner.providers.openquantum.credits.get_remaining_credits",
        lambda cfg, timeout_s=None: 80.0,
    )
    below, remaining = below_min_credits(_cfg(min_credits=100.0))
    assert below is True
    assert remaining == 80.0


def test_rate_limit_threshold(monkeypatch):
    monkeypatch.setattr(
        "qbittensor.miner.providers.openquantum.credits.get_remaining_credits",
        lambda cfg, timeout_s=None: 150.0,
    )
    assert should_rate_limit_for_low_credits(_cfg(min_credits=100.0)) is False
    monkeypatch.setattr(
        "qbittensor.miner.providers.openquantum.credits.get_remaining_credits",
        lambda cfg, timeout_s=None: 99.0,
    )
    assert should_rate_limit_for_low_credits(_cfg(min_credits=100.0)) is True
