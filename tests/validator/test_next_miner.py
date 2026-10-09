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

"""Tests for NextMiner round-robin and invalid-axon filtering."""

import bittensor as bt

from qbittensor.validator.miner_manager.next_miner import NextMiner
from tests.test_utils import get_mock_metagraph


def _axon(ip: str = "203.0.113.10", port: int = 8091, hotkey: str = "hk") -> bt.AxonInfo:
    return bt.AxonInfo(
        version=4,
        ip=ip,
        port=port,
        ip_type=4,
        hotkey=hotkey,
        coldkey="ck",
    )


def test_skips_invalid_axons_and_returns_valid():
    mg = get_mock_metagraph(num_axons=4)
    mg.axons = [
        _axon(ip="0.0.0.0", port=8091),  # placeholder IP (also not serving)
        _axon(ip="1.2.3.4", port=0),     # port 0
        _axon(ip="203.0.113.10", port=8091, hotkey="hk2"),
        _axon(ip="0.0.0.0", port=0),     # both bad
    ]
    nm = NextMiner(mg)

    miner = nm.get_next_miner()
    assert miner is not None
    assert miner.uid == 2
    assert miner.hotkey == "hk2"


def test_returns_none_when_all_axons_invalid():
    mg = get_mock_metagraph(num_axons=3)
    mg.axons = [_axon(ip="0.0.0.0", port=0) for _ in range(3)]
    nm = NextMiner(mg)

    assert nm.get_next_miner() is None
    # Index advanced a full cycle and is ready for the next call
    assert nm._index == 0


def test_timeout_backoff_skips_then_expires(monkeypatch):
    mg = get_mock_metagraph(num_axons=1)
    mg.axons = [_axon(hotkey="hk0")]
    rng = __import__("random").Random(0)
    nm = NextMiner(mg, rng=rng)
    assert nm.record_timeout("hk0") is None
    assert nm.get_next_miner() is not None
    delay = nm.record_timeout("hk0")
    assert delay is not None
    assert 45 * 60 - 2 <= delay <= 75 * 60 + 2
    assert nm.is_backed_off("hk0")
    delay = nm._backoff_until["hk0"] - __import__("time").time()
    assert 45 * 60 - 2 <= delay <= 75 * 60 + 2
    assert nm.get_next_miner() is None
    assert nm.list_serving_miners() == []
    nm._backoff_until["hk0"] = 0
    assert nm._timeouts["hk0"] == 2
    assert nm.is_backed_off("hk0") is False
    assert "hk0" not in nm._timeouts
    assert nm.record_timeout("hk0") is None
    assert nm.is_backed_off("hk0") is False
    assert nm.get_next_miner() is not None


def test_inflight_miner_returns_to_sweep_before_assignment_backoff():
    """Long backoff blocks new work. Collect retry is 60–120s."""
    mg = get_mock_metagraph(num_axons=1)
    mg.axons = [_axon(hotkey="hk0")]
    rng = __import__("random").Random(0)
    nm = NextMiner(mg, rng=rng)
    assert nm.record_timeout("hk0", inflight=True) is None
    delay = nm.record_timeout("hk0", inflight=True)
    assert delay is not None
    assert 45 * 60 - 2 <= delay <= 75 * 60 + 2
    assert nm.is_backed_off("hk0")
    assert nm.get_next_miner() is None
    hb = nm._heartbeat_backoff_until["hk0"] - __import__("time").time()
    assert 60 - 2 <= hb <= 120 + 2
    assert nm.list_serving_miners(heartbeat_hotkeys={"hk0"}) == []
    nm._heartbeat_backoff_until["hk0"] = 0
    serving = nm.list_serving_miners(heartbeat_hotkeys={"hk0"})
    assert [m.hotkey for m in serving] == ["hk0"]
    assert nm.get_next_miner() is None
    nm.record_success("hk0")
    assert nm.is_backed_off("hk0") is False
    assert nm.get_next_miner() is not None


def test_returns_none_for_empty_metagraph():
    mg = get_mock_metagraph(num_axons=0)
    nm = NextMiner(mg)
    assert nm.get_next_miner() is None


def test_round_robin_only_among_valid_axons():
    mg = get_mock_metagraph(num_axons=4)
    mg.axons = [
        _axon(ip="1.1.1.1", hotkey="hk0"),
        _axon(ip="0.0.0.0"),
        _axon(ip="2.2.2.2", hotkey="hk2"),
        _axon(ip="0.0.0.0"),
    ]
    nm = NextMiner(mg)

    first = nm.get_next_miner()
    second = nm.get_next_miner()
    third = nm.get_next_miner()

    assert first is not None and first.uid == 0
    assert second is not None and second.uid == 2
    # wraps back to first valid
    assert third is not None and third.uid == 0


def test_mock_metagraph_defaults_are_valid():
    """get_mock_metagraph axons should pass the validity guard."""
    mg = get_mock_metagraph(num_axons=2)
    nm = NextMiner(mg)
    m1 = nm.get_next_miner()
    m2 = nm.get_next_miner()
    assert m1 is not None and m1.uid == 0
    assert m2 is not None and m2.uid == 1


def test_queries_permitted_high_stake_hotkeys():
    """A validator permit and stake above 4096 still leave a serving axon eligible."""
    mg = get_mock_metagraph(num_axons=3)
    mg.axons = [
        _axon(ip="1.1.1.1", hotkey="hk0"),
        _axon(ip="2.2.2.2", hotkey="hk1"),
        _axon(ip="3.3.3.3", hotkey="hk2"),
    ]
    mg.validator_permit = [True, False, True]
    mg.S = [30_528.0, 1.0, 7_089.0]

    nm = NextMiner(mg)

    first = nm.get_next_miner()
    second = nm.get_next_miner()
    third = nm.get_next_miner()
    assert first is not None and first.uid == 0
    assert second is not None and second.uid == 1
    assert third is not None and third.uid == 2
    assert [m.uid for m in nm.list_serving_miners()] == [0, 1, 2]


def test_permitted_hotkeys_remain_when_every_uid_has_a_permit():
    mg = get_mock_metagraph(num_axons=2)
    mg.axons = [
        _axon(ip="1.1.1.1", hotkey="hk0"),
        _axon(ip="2.2.2.2", hotkey="hk1"),
    ]
    mg.validator_permit = [True, True]
    mg.S = [30_528.0, 2_345_649.0]

    nm = NextMiner(mg)
    assert nm.get_next_miner() is not None
    assert [m.hotkey for m in nm.list_serving_miners()] == ["hk0", "hk1"]
