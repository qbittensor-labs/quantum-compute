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

from qbittensor.database.database_manager import DatabaseManager
from qbittensor.validator.miner_manager.capabilities import (
    ban_miner,
    get_placeable_classes,
    has_capability_record,
    is_banned,
    upsert_capabilities,
)
from qbittensor.validator.miner_manager.next_miner import NextMiner
from tests.test_utils import get_mock_metagraph


def test_upsert_and_placeable(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    db = DatabaseManager("validator_cap_placeable")
    assert get_placeable_classes(db) == {}
    upsert_capabilities(db, "hk0", ["ionq:forte-1", "quantumrings:qasm3"])
    placeable = get_placeable_classes(db)
    assert placeable["hk0"] == ["ionq:forte-1", "quantumrings:qasm3"]


def test_empty_cache_no_classes(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    db = DatabaseManager("validator_cap_empty")
    assert get_placeable_classes(db) == {}


def test_stale_capabilities_dropped(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    db = DatabaseManager("validator_cap_stale")
    upsert_capabilities(db, "hk0", ["ionq:forte-1"])
    db.query_and_commit_with_values(
        "UPDATE miner_capabilities SET updated_at=? WHERE hotkey=?",
        ("2000-01-01 00:00:00", "hk0"),
    )
    assert get_placeable_classes(db, ttl_seconds=600) == {}


def test_ban_miner(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    db = DatabaseManager("validator_cap_ban")
    assert is_banned(db, "hk0") is False
    ban_miner(db, "hk0", "never_complete", hours=2)
    assert is_banned(db, "hk0") is True


def test_next_miner_skips_missing_class_and_banned(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PUBLIC_BACKEND_CLASSES", raising=False)
    db = DatabaseManager("validator_cap_next")
    mg = get_mock_metagraph(num_axons=3)
    upsert_capabilities(db, "hk0", ["ionq:forte-1"])
    upsert_capabilities(db, "hk1", ["quantumrings:qasm3"])
    ban_miner(db, "hk1", "counts_invalid", hours=24)

    nm = NextMiner(mg)
    miner = nm.get_next_miner_for_class("ionq:forte-1", db)
    assert miner is not None
    assert miner.hotkey == "hk0"

    nm2 = NextMiner(mg)
    skipped = nm2.get_next_miner_for_class("quantumrings:qasm3", db)
    assert skipped is None

    nm3 = NextMiner(mg)
    none = nm3.get_next_miner_for_class("rigetti:ankaa-3", db)
    assert none is None


def test_next_miner_empty_cache_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PUBLIC_BACKEND_CLASSES", raising=False)
    db = DatabaseManager("validator_cap_none")
    nm = NextMiner(get_mock_metagraph(num_axons=3))
    assert nm.get_next_miner_for_class(None, db) is None
    assert nm.get_next_miner() is not None


def test_next_miner_skips_empty_advertised_capabilities_even_with_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_BACKEND_CLASSES", "quantumrings:qasm3")
    db = DatabaseManager("validator_cap_empty_probe")
    upsert_capabilities(db, "hk1", [])
    upsert_capabilities(db, "hk0", ["quantumrings:qasm3"])
    assert has_capability_record(db, "hk1") is True
    nm = NextMiner(get_mock_metagraph(num_axons=3))
    seen = [nm.get_next_miner_for_class(None, db).hotkey for _ in range(6)]
    assert "hk1" not in seen
    assert "hk0" in seen
    assert "hk2" in seen


def test_dispatch_odds_are_linear_in_stake(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_BACKEND_CLASSES", "quantumrings:qasm3")
    monkeypatch.setenv("WEIGHT_STAKE_EXPONENT", "0.5")
    monkeypatch.delenv("DISPATCH_STAKE_EXPONENT", raising=False)
    db = DatabaseManager("validator_cap_linear")
    upsert_capabilities(db, "hk0", ["quantumrings:qasm3"])
    upsert_capabilities(db, "hk1", ["quantumrings:qasm3"])
    mg = get_mock_metagraph(num_axons=2)
    mg.S = [10_000.0, 100_000.0]
    nm = NextMiner(mg, rng=__import__("random").Random(0), min_stake_alpha=0)
    assert nm.stake_exponent == 1.0
    picks = [nm.get_next_miner_for_class(None, db).hotkey for _ in range(2000)]
    assert abs(picks.count("hk1") / 2000 - 10 / 11) < 0.04


def test_class_claim_prefers_higher_stake(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_BACKEND_CLASSES", "quantumrings:qasm3")
    db = DatabaseManager("validator_cap_stake")
    upsert_capabilities(db, "hk0", ["quantumrings:qasm3"])
    upsert_capabilities(db, "hk1", ["quantumrings:qasm3"])
    upsert_capabilities(db, "hk2", ["quantumrings:qasm3"])
    mg = get_mock_metagraph(num_axons=3)
    mg.S = [1.0, 10_000.0, 1.0]
    nm = NextMiner(mg, rng=__import__("random").Random(0), stake_exponent=0.5)
    picks = [nm.get_next_miner_for_class(None, db).hotkey for _ in range(40)]
    assert picks.count("hk1") > picks.count("hk0")
    assert picks.count("hk1") > picks.count("hk2")


def test_stale_empty_capability_record_is_probed_again(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_BACKEND_CLASSES", "quantumrings:qasm3")
    db = DatabaseManager("validator_cap_stale_empty")
    upsert_capabilities(db, "hk1", [])
    db.query_and_commit_with_values(
        "UPDATE miner_capabilities SET updated_at=? WHERE hotkey=?",
        ("2000-01-01 00:00:00", "hk1"),
    )
    assert has_capability_record(db, "hk1") is False
    upsert_capabilities(db, "hk0", ["quantumrings:qasm3"])
    nm = NextMiner(get_mock_metagraph(num_axons=3), rng=__import__("random").Random(0))
    seen = {nm.get_next_miner_for_class(None, db).hotkey for _ in range(30)}
    assert "hk1" in seen


def test_class_claim_includes_permitted_high_stake(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_BACKEND_CLASSES", "quantumrings:qasm3")
    db = DatabaseManager("validator_cap_permit")
    upsert_capabilities(db, "hk0", ["quantumrings:qasm3"])
    mg = get_mock_metagraph(num_axons=1)
    mg.validator_permit = [True]
    mg.S = [30_528.0]
    nm = NextMiner(mg, min_stake_alpha=5000.0)
    picks = {nm.get_next_miner_for_class(None, db).hotkey for _ in range(5)}
    assert picks == {"hk0"}
    assert [m.hotkey for m in nm.list_serving_miners(db)] == ["hk0"]


def test_next_miner_stake_floor_skips_dust(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_BACKEND_CLASSES", "quantumrings:qasm3")
    monkeypatch.setenv("WEIGHT_MIN_MINER_STAKE_ALPHA", "5000")
    db = DatabaseManager("validator_cap_floor")
    upsert_capabilities(db, "hk0", ["quantumrings:qasm3"])
    upsert_capabilities(db, "hk1", ["quantumrings:qasm3"])
    upsert_capabilities(db, "hk2", ["quantumrings:qasm3"])
    mg = get_mock_metagraph(num_axons=3)
    mg.S = [1.0, 10_000.0, 4_999.0]
    nm = NextMiner(mg, rng=__import__("random").Random(0), min_stake_alpha=5000.0)
    picks = {nm.get_next_miner_for_class(None, db).hotkey for _ in range(20)}
    assert picks == {"hk1"}


def test_next_miner_probes_uncached_when_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_BACKEND_CLASSES", "quantumrings:qasm3")
    db = DatabaseManager("validator_cap_probe")
    upsert_capabilities(db, "hk0", ["quantumrings:qasm3"])
    nm = NextMiner(get_mock_metagraph(num_axons=3), rng=__import__("random").Random(1))
    hotkeys = {
        nm.get_next_miner_for_class(None, db).hotkey for _ in range(30)
    }
    assert "hk0" in hotkeys
    assert "hk1" in hotkeys
    assert "hk2" in hotkeys
