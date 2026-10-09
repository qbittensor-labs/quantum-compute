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

from types import SimpleNamespace
from unittest.mock import Mock

from neurons.validator import Validator
from qbittensor.database.database_manager import DatabaseManager
from qbittensor.validator.miner_manager.capabilities import (
    has_capability_record,
    upsert_capabilities,
)


def _dummy_validator(db=None) -> Validator:
    v = object.__new__(Validator)
    v.job_client = Mock()
    v.dendrite = Mock()
    v.scorer = Mock()
    v.database_manager = db
    v.synapse_manager = Mock()
    v.next_miner = Mock()
    return v


def test_empty_capabilities_does_not_claim(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PUBLIC_BACKEND_CLASSES", raising=False)
    db = DatabaseManager("validator_empty_claim")
    v = _dummy_validator(db)
    v.next_miner.get_next_miner.return_value = None
    v._forward_class_claim("t")
    v.synapse_manager.get_synapse_for_classes.assert_not_called()
    v.job_client.get_execution_for_classes.assert_not_called()
    v.job_client.report_spark.assert_not_called()


def test_empty_cached_capabilities_does_not_claim(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PUBLIC_BACKEND_CLASSES", raising=False)
    db = DatabaseManager("validator_empty_caps_claim")
    upsert_capabilities(db, "hk0", [])
    v = _dummy_validator(db)
    v.next_miner.get_next_miner.return_value = None
    v.next_miner.get_next_miner_for_class.return_value = None
    v._forward_class_claim("t")
    v.synapse_manager.get_synapse_for_classes.assert_not_called()
    v.job_client.get_execution_for_classes.assert_not_called()


def test_failed_synapse_does_not_cache_empty_capabilities(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    db = DatabaseManager("validator_fail_caps")
    v = _dummy_validator(db)
    miner = SimpleNamespace(hotkey="hk1", axon=Mock(), uid=1)
    failed = SimpleNamespace(success=False, capabilities=[])
    v._upsert_capabilities_from_responses([failed], miner)
    assert has_capability_record(db, "hk1") is False
    ok = SimpleNamespace(success=True, capabilities=["quantumrings:qasm3"])
    v._upsert_capabilities_from_responses([ok], miner)
    assert has_capability_record(db, "hk1") is True


def test_invalid_ca_proof_bans_miner_and_fails_job(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from qbittensor.protocol import ExecutionData
    from qbittensor.validator.reward.score import Scorer
    from qbittensor.validator.miner_manager.capabilities import is_banned
    from qbittensor.validator.utils.execution_status import ExecutionStatus
    from unittest.mock import Mock

    db = DatabaseManager("validator_ban_proof")
    tel = Mock()
    jobc = Mock()
    jobc.verify_ca_proof.return_value = False
    jobc.fetch_certificate_pem.return_value = None
    scorer = Scorer(db, Mock(), telemetry_service=tel, job_client=jobc)
    execution = ExecutionData(
        execution_id="exec-1",
        shots=100,
        upload_data_id="up-1",
        execution_data={
            "proof": {
                "statement": "pot.job.v1",
                "signature": "sig",
                "certificate_pem": "-----BEGIN CERTIFICATE-----\nM\n-----END CERTIFICATE-----",
            }
        },
        status=ExecutionStatus.COMPLETED,
        errorMessage=None,
    )
    assert scorer._patch_job_complete(execution, "hk-bad") is False
    assert is_banned(db, "hk-bad") is True
    jobc.patch_execution.assert_called()
    body = jobc.patch_execution.call_args[0][1]
    assert body["status"] in ("Failed", ExecutionStatus.FAILED)


def test_class_claim_reports_spark_on_204(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PUBLIC_BACKEND_CLASSES", raising=False)
    db = DatabaseManager("validator_claim_204")
    upsert_capabilities(db, "hk0", ["quantumrings:qasm3"])
    v = _dummy_validator(db)
    miner = SimpleNamespace(hotkey="hk0", axon=Mock(), uid=1)
    v.next_miner.get_next_miner_for_class.return_value = miner
    v.synapse_manager.get_synapse_for_classes.return_value = (None, None)
    v.synapse_manager.collect_only_synapse.return_value = (Mock(), Mock())
    v.next_miner.get_next_miner.return_value = miner
    v.dendrite.query.return_value = []
    v._forward_class_claim("t", {"hk0"})
    v.synapse_manager.get_synapse_for_classes.assert_called_once()
    args, kwargs = v.synapse_manager.get_synapse_for_classes.call_args
    assert args[0] == ["quantumrings:qasm3"]
    assert kwargs.get("actor_id") == "hk0"
    v.job_client.report_spark.assert_called_once_with(["quantumrings:qasm3"])


def test_sweep_leaves_rate_limited_miners_out_of_class_claim(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    db = DatabaseManager("validator_sweep_credits")
    v = _dummy_validator(db)
    broke = SimpleNamespace(hotkey="broke", axon=Mock(), uid=1)
    solvent = SimpleNamespace(hotkey="ok", axon=Mock(), uid=2)
    v.next_miner.list_serving_miners.return_value = [broke, solvent]
    v._inflight_hotkeys = lambda: set()
    v.synapse_manager.collect_only_synapse.return_value = (Mock(), Mock())
    broke_resp = SimpleNamespace(
        success=True,
        rate_limited=True,
        capabilities=["quantumrings:qasm3"],
        dendrite=SimpleNamespace(status_code=200),
    )
    ok_resp = SimpleNamespace(
        success=True,
        rate_limited=False,
        capabilities=["quantumrings:qasm3"],
        dendrite=SimpleNamespace(status_code=200),
    )
    v.dendrite.query.return_value = [broke_resp, ok_resp]
    v._upsert_capabilities_from_responses = Mock()

    willing = v._sweep_running_jobs("t")

    assert willing == {"ok"}
    v.next_miner.record_success.assert_any_call("broke")
    v.next_miner.record_success.assert_any_call("ok")
    assert v.scorer.process_miner_responses.call_count == 2


def test_class_claim_skips_a_miner_who_did_not_answer(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PUBLIC_BACKEND_CLASSES", raising=False)
    db = DatabaseManager("validator_claim_unanswered")
    upsert_capabilities(db, "hk0", ["quantumrings:qasm3"])
    v = _dummy_validator(db)
    miner = SimpleNamespace(hotkey="hk0", axon=Mock(), uid=1)
    v.next_miner.get_next_miner_for_class.return_value = miner
    v.next_miner.get_next_miner.return_value = None
    v._forward_class_claim("t", set())
    v.synapse_manager.get_synapse_for_classes.assert_not_called()
    v.job_client.report_spark.assert_not_called()
