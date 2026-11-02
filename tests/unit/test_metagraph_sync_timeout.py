# The MIT License (MIT)
# Copyright © 2026 qBitTensor Labs

from unittest.mock import patch

import pytest

from qbittensor.bt_compat import MetagraphAdapter
from qbittensor.utils.neuron_liveness import neuron_progress_is_stale, touch_neuron_progress


class _Subtensor:
    def __init__(self, metagraph):
        self.calls = []
        self._metagraph = metagraph
        self.subnets = self

    def metagraph(self, **kwargs):
        self.calls.append(kwargs)
        value = self._metagraph
        if callable(value):
            return value(**kwargs)
        return value


def _adapter() -> MetagraphAdapter:
    adapter = MetagraphAdapter.__new__(MetagraphAdapter)
    adapter.netuid = 48
    adapter.subtensor = None
    adapter._mg = "old"
    return adapter


def test_lite_sync_skips_commitments():
    sub = _Subtensor(metagraph="graph")
    adapter = _adapter()
    with patch.object(MetagraphAdapter, "_rebuild"):
        adapter.sync(subtensor=sub, lite=True, block=10)
    assert sub.calls == [{"netuid": 48, "commitments": False, "block": 10}]
    assert adapter._mg == "graph"
    assert adapter.subtensor is sub


def test_full_sync_keeps_commitments():
    sub = _Subtensor(metagraph="graph")
    adapter = _adapter()
    with patch.object(MetagraphAdapter, "_rebuild"):
        adapter.sync(subtensor=sub, lite=False)
    assert sub.calls == [{"netuid": 48}]


def test_sync_timeout_does_not_apply_a_late_metagraph(monkeypatch):
    monkeypatch.setattr("qbittensor.bt_compat.METAGRAPH_SYNC_TIMEOUT_S", 0.05)

    def _hang(**_kwargs):
        import time
        time.sleep(2)
        return "late"

    sub = _Subtensor(metagraph=_hang)
    adapter = _adapter()
    with patch.object(MetagraphAdapter, "_rebuild") as rebuild:
        with pytest.raises(TimeoutError, match="metagraph sync exceeded"):
            adapter.sync(subtensor=sub)
    assert adapter._mg == "old"
    rebuild.assert_not_called()


def test_sync_falls_back_when_sdk_has_no_commitments_flag():
    class _Old:
        def __init__(self):
            self.calls = []
            self.subnets = self

        def metagraph(self, **kwargs):
            self.calls.append(kwargs)
            if "commitments" in kwargs:
                raise TypeError("unexpected keyword argument 'commitments'")
            return "graph"

    sub = _Old()
    adapter = _adapter()
    with patch.object(MetagraphAdapter, "_rebuild"):
        adapter.sync(subtensor=sub, lite=True)
    assert sub.calls[0]["commitments"] is False
    assert "commitments" not in sub.calls[1]
    assert adapter._mg == "graph"


def test_neuron_progress_staleness(monkeypatch):
    import qbittensor.utils.neuron_liveness as liveness

    monkeypatch.setattr(liveness, "_progress_at", None)
    assert neuron_progress_is_stale(1) is False
    touch_neuron_progress()
    assert neuron_progress_is_stale(60) is False
    monkeypatch.setattr(liveness, "_progress_at", 0.0)
    monkeypatch.setattr(liveness.time, "monotonic", lambda: 120.0)
    assert neuron_progress_is_stale(60) is True
