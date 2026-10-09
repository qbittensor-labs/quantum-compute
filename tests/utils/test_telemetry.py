from unittest.mock import Mock

from qbittensor.protocol import COLLECT_SYNAPSE_ID
from qbittensor.utils.services.telemetry import TelemetryService, emit_from_registry


def _svc() -> TelemetryService:
    return TelemetryService.__new__(TelemetryService)


def test_format_batch_puts_subject_hotkey_in_attributes():
    svc = _svc()
    formatted = svc._format_batch(
        [
            {
                "type": "vali_ban",
                "timestamp": "2026-01-01T00:00:00Z",
                "value": "bad_proof",
                "miner_uid": 3,
                "miner_hotkey": "hk",
                "attributes": {"hours": 24, "execution_id": "exec-1"},
            }
        ]
    )
    assert formatted == [
        {
            "type": "vali_ban",
            "timestamp": "2026-01-01T00:00:00Z",
            "string_value": "bad_proof",
            "attributes": {
                "hours": 24,
                "execution_id": "exec-1",
                "miner_hotkey": "hk",
            },
        }
    ]
    assert "miner_uid" not in formatted[0]
    assert "miner_hotkey" not in formatted[0]


def test_format_batch_sends_numbers_as_numeric_value():
    svc = _svc()
    formatted = svc._format_batch(
        [
            {
                "type": "vali_axon_backoff",
                "timestamp": "t",
                "value": 3600.0,
                "miner_uid": 1,
                "miner_hotkey": "hk",
                "attributes": None,
            }
        ]
    )
    assert formatted[0]["numeric_value"] == 3600.0
    assert "string_value" not in formatted[0]
    assert formatted[0]["attributes"] == {"miner_hotkey": "hk"}
    assert "miner_uid" not in formatted[0]


def test_handout_emits_execution_id_string_on_real_claim():
    svc = _svc()
    svc.queue = __import__("queue").Queue()
    svc.vali_record_execution_from_jobs_api("exec-real", "hk2")
    types = []
    while not svc.queue.empty():
        types.append(svc.queue.get_nowait())
    kinds = {item["type"]: item["value"] for item in types}
    assert kinds["vali_execution_from_jobs_api"] == 1.0
    assert kinds["vali_handout"] == "exec-real"
    assert all(item["attributes"]["miner_hotkey"] == "hk2" for item in types)
    assert all("miner_uid" not in item for item in types)


def test_handout_skips_collect_only():
    svc = _svc()
    svc.queue = __import__("queue").Queue()
    svc.vali_record_execution_from_jobs_api(COLLECT_SYNAPSE_ID, "hk2")
    items = []
    while not svc.queue.empty():
        items.append(svc.queue.get_nowait())
    assert [i["type"] for i in items] == ["vali_execution_from_jobs_api"]
    assert items[0]["value"] == 0.0
    assert items[0]["attributes"]["miner_hotkey"] == "hk2"


def test_emit_from_registry_noops_without_service():
    emit_from_registry(object(), "miner_record_private_submit", "e", "p")


def test_emit_from_registry_does_not_stamp_miner_identity():
    tel = Mock()
    registry = Mock()
    registry._telemetry_service = tel
    registry._miner_uid = 7
    registry.keypair = Mock(ss58_address="miner-hk")
    emit_from_registry(registry, "miner_record_private_submit", "exec-1", "priv-9")
    tel.miner_record_private_submit.assert_called_once_with("exec-1", "priv-9")
