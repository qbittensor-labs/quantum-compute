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

import threading
import time
from enum import Enum
from typing import Any, Dict, List, Tuple
import bittensor as bt
from qbittensor.database.database_manager import DatabaseManager
from qbittensor.protocol import COLLECT_SYNAPSE_ID, CircuitSynapse, ExecutionData
from qbittensor.utils.services.telemetry import TelemetryService
from qbittensor.utils.time import timestamp_str
from qbittensor.validator.compute_request.compute_request import ComputeRequest
from qbittensor.utils.services.exceptions import JobApiError
from qbittensor.utils.services.job import JobClient
from qbittensor.validator.miner_manager.next_miner import BasicMiner
from qbittensor.validator.utils.execution_status import ExecutionStatus
from qbittensor.validator.miner_manager.capabilities import (
    LEASE_BAN_HOURS,
    PROOF_BAN_HOURS,
    ban_miner,
)
from qbittensor.validator.utils.execution_metrics import ExecutionMetrics

# Matches Jobs PUBLIC_EXECUTION_LEASE_TTL_MS (45 minutes).
PUBLIC_LEASE_SECONDS = 45 * 60
_PROOF_CHEAT_MARKERS = (
    "already bound to another execution",
    "proof hashes do not match",
    "proof signature is invalid",
    "requires a private-job execution proof",
    "backend class does not match",
)


class Scorer:

    def __init__(
        self,
        database_manager: DatabaseManager,
        metagraph: bt.Metagraph,
        telemetry_service: TelemetryService | None = None,
        job_client: JobClient | None = None,
    ):
        self.database_manager: DatabaseManager = database_manager
        self.metagraph: bt.Metagraph = metagraph
        self.job_client = job_client
        self._metrics: ExecutionMetrics = ExecutionMetrics(database_manager)
        if telemetry_service is None:
            raise ValueError("telemetry_service is required (use typed client from neurons)")
        self.telemetry_service = telemetry_service
        self._last_active: Dict[str, set[str]] = {}
        # execution_id -> (miner_hotkey, last_heartbeat_unix)
        self._inflight_seen: Dict[str, Tuple[str, float]] = {}
        # Executions this validator sent. Only these may be patched lease_expired.
        self._assigned: set[str] = set()
        self._load_inflight()

    def process_miner_responses(
            self,
            responses: List[CircuitSynapse],
            next_miner: BasicMiner,
            original_compute_request_data: ComputeRequest):
        """Process responses from every miner"""
        current_thread: str = threading.current_thread().name

        for synapse in responses:
            self.telemetry_service.vali_record_synapse_response(
                execution_id=synapse.execution_id,
                miner_hotkey=next_miner.hotkey,
                error_message=synapse.error_message,
                success=synapse.success,
                rate_limited=synapse.rate_limited
            )
            try:
                # Handle miner disconnected. Currently using `success` field in the
                # synapse. This will cause a retry with the original compute request
                if not synapse.success:
                    if synapse.error_message:
                        bt.logging.info(
                            f"| {current_thread} | ❗ Synapse error message from miner "
                            f"'{next_miner.hotkey}': {synapse.error_message}"
                        )
                    if synapse.execution_id != COLLECT_SYNAPSE_ID:
                        self.telemetry_service.vali_record_no_response(
                            next_miner.hotkey,
                            synapse.execution_id,
                        )
                    # The miner never accepted. This does not spend a job attempt.
                    self._patch_job_rejected(
                        synapse.execution_id, "Miner did not respond"
                    )
                    bt.logging.info(
                        f"| {current_thread} | ❗ Synapse success field is false from miner "
                        f"'{next_miner.hotkey}'."
                    )
                    continue

                # If we got rate limited, push this circuit back on the queue. This will
                # cause a retry with the original compute request
                if synapse.rate_limited:
                    if synapse.execution_id != COLLECT_SYNAPSE_ID:
                        self.telemetry_service.vali_record_rate_limited(
                            next_miner.hotkey,
                            synapse.execution_id,
                        )
                    self._patch_job_rejected(synapse.execution_id, "Miner is rate limiting")
                    bt.logging.trace(
                        f"| {current_thread} | 🚦 Handling rate limited request {original_compute_request_data}.")

                else:
                    if original_compute_request_data.execution_id != COLLECT_SYNAPSE_ID:
                        self._patch_execution_status(
                            original_compute_request_data.execution_id, synapse.execution_status)
                        self._record_execution(
                            next_miner.hotkey,
                            original_compute_request_data.execution_id,
                            original_compute_request_data.shots)
                    seen_active: set[str] = set()
                    for active in synapse.active_executions or []:
                        if active.execution_id == COLLECT_SYNAPSE_ID:
                            continue
                        if active.status in (
                            ExecutionStatus.PENDING,
                            ExecutionStatus.QUEUED,
                            ExecutionStatus.RUNNING,
                        ):
                            seen_active.add(active.execution_id)
                            self._patch_execution_status(
                                active.execution_id, active.status)
                    finished_ids = {
                        e.execution_id
                        for e in (synapse.finished_executions or [])
                        if e.execution_id and e.execution_id != COLLECT_SYNAPSE_ID
                    }
                    prev = self._last_active.get(next_miner.hotkey, set())
                    dropped = prev - seen_active - finished_ids
                    for eid in dropped:
                        bt.logging.warning(
                            f"| {current_thread} | Miner {next_miner.hotkey[:8]}... "
                            f"dropped in-flight {eid}"
                        )
                        self._clear_inflight(eid)
                        self.telemetry_service.vali_record_dropped_inflight(
                            next_miner.hotkey, eid
                        )
                        self._patch_job_rejected(eid, "Dropped in-flight work")
                    self._last_active[next_miner.hotkey] = seen_active
                    for eid in seen_active:
                        self._note_inflight(next_miner.hotkey, eid)

                # If no finished executions, we don't want to update the last circuit table
                if synapse.finished_executions is None or len(synapse.finished_executions) == 0:
                    bt.logging.trace(f"| {current_thread} | ⚠️  No finished executions in this response")
                    continue

                num_pending = sum(1 for exec in synapse.finished_executions if exec.status == ExecutionStatus.PENDING)
                num_queued = sum(1 for exec in synapse.finished_executions if exec.status == ExecutionStatus.QUEUED)
                num_running = sum(1 for exec in synapse.finished_executions if exec.status == ExecutionStatus.RUNNING)
                num_failed = sum(1 for exec in synapse.finished_executions if exec.status == ExecutionStatus.FAILED)
                num_completed = sum(
                    1 for exec in synapse.finished_executions
                    if exec.status == ExecutionStatus.COMPLETED
                )

                bt.logging.trace(f"| {current_thread} | 📊  Finished executions detail\n----------------------------\n⭐  Number of completed executions: {num_completed}\n🚩  Number of failed executions: {num_failed}\n▶️  Number of running executions: {num_running}\n⏳   Number of queued executions: {num_queued}\n⏸️   Number of pending executions: {num_pending}\n----------------------------")

                patch_ok = True
                for execution in synapse.finished_executions:
                    try:
                        self.telemetry_service.vali_record_execution_from_miner(
                            execution_id=execution.execution_id,
                            status=execution.status,
                            miner_hotkey=next_miner.hotkey,
                        )
                        if execution.status == ExecutionStatus.COMPLETED:
                            self._record_time_received(
                                next_miner.hotkey, execution.execution_id)
                            self._clear_inflight(execution.execution_id)
                            if not self._patch_job_complete(execution, next_miner.hotkey):
                                patch_ok = False
                                continue
                            self.telemetry_service.vali_record_complete(
                                next_miner.hotkey,
                                execution.execution_id,
                            )
                            bt.logging.trace(
                                f"| {current_thread} | ✅  Miner reported successfuly completion "
                                f"for execution_id {execution.execution_id}"
                            )
                        elif execution.status == ExecutionStatus.FAILED:
                            error_msg = execution.errorMessage if execution.errorMessage else "Miner reported failure"
                            self._clear_inflight(execution.execution_id)
                            self.telemetry_service.vali_record_miner_failed(
                                next_miner.hotkey,
                                execution.execution_id,
                                error_msg,
                            )
                            if not self._patch_job_rejected(
                                execution.execution_id, error_msg, execution.execution_data
                            ):
                                patch_ok = False
                                continue
                            bt.logging.trace(
                                f"| {current_thread} | ❌  Miner reported failure for execution_id "
                                f"{execution.execution_id} with message: {error_msg}"
                            )

                    except Exception as e:
                        patch_ok = False
                        bt.logging.error(
                            f"| {current_thread} | ❌ Error processing finished execution "
                            f"execution_id={execution.execution_id} err={e}"
                        )

                # Jobs is the ledger. Only advance the local watermark after every
                # finished row in this synapse patched successfully so a 400 can retry.
                if patch_ok:
                    self._metrics.upsert_last_circuit(next_miner.hotkey, synapse.last_circuit)

            except Exception as e:
                bt.logging.error(f"| {current_thread} | ❌ Error handling miner response: {e}")

    def _patch_job_rejected(self, execution_id: str, message: str, execution_data: object | None = None) -> bool:
        """Send the request back to the job server because retries exceeded.

        A nested proof makes Jobs require upload_id and re-check the signature,
        so a real failure never lands. Drop the proof and keep the rest.
        """
        self._clear_inflight(execution_id)
        body: Dict[str, Any] = {
            "status": ExecutionStatus.FAILED,
            "message": message,
            "execution_data": self._failure_execution_data(execution_data),
        }
        return self._patch(execution_id, body)

    @staticmethod
    def _failure_execution_data(execution_data: object | None) -> object:
        if not isinstance(execution_data, dict) or "proof" not in execution_data:
            return {} if execution_data is None else execution_data
        cleaned = dict(execution_data)
        cleaned.pop("proof", None)
        return cleaned

    def _patch_job_complete(self, execution: ExecutionData, miner_hotkey: str | None = None) -> bool:
        """Submit the execution to the job server"""
        if not execution.upload_data_id:
            bt.logging.debug(
                f"❗ Cannot patch job complete for execution {execution.execution_id} "
                f"because upload_data_id is missing"
            )
            return False
        data = execution.execution_data if isinstance(execution.execution_data, dict) else {}
        proof = data.get("proof") if isinstance(data.get("proof"), dict) else None
        if proof:
            statement = proof.get("statement")
            signature = proof.get("signature")
            pem = proof.get("certificate_pem")
            serial = proof.get("certificate_serial")
            if not pem and isinstance(serial, str) and self.job_client is not None:
                pem = self.job_client.fetch_certificate_pem(serial)
            if isinstance(statement, str) and isinstance(signature, str) and isinstance(pem, str):
                if not self.job_client.verify_ca_proof(statement, signature, pem):
                    bt.logging.warning(
                        f"❗ CA rejected private-job proof for execution {execution.execution_id}"
                    )
                    self._ban_for_proof(
                        miner_hotkey, "bad_proof", execution.execution_id
                    )
                    self._patch_job_rejected(
                        execution.execution_id,
                        "Invalid private-job proof",
                        execution.execution_data,
                    )
                    return False
        body: Dict[str, Any] = {
            "status": ExecutionStatus.COMPLETED,
            "upload_id": execution.upload_data_id,
            "execution_data": execution.execution_data
        }
        if proof:
            signature = proof.get("signature")
            pem = proof.get("certificate_pem")
            serial = proof.get("certificate_serial")
            if not pem and isinstance(serial, str) and self.job_client is not None:
                pem = self.job_client.fetch_certificate_pem(serial)
            if isinstance(signature, str):
                body["proof_signature"] = signature
            if isinstance(pem, str):
                body["proof_certificate_pem"] = pem
        try:
            payload = dict(body)
            if "status" in payload:
                payload["status"] = self._status_value(payload["status"])
            self.job_client.patch_execution(execution.execution_id, payload)
            return True
        except JobApiError as err:
            if miner_hotkey and self._is_proof_cheat(err):
                reason = (
                    "proof_replay"
                    if "already bound" in self._proof_error_text(err)
                    else "bad_proof"
                )
                self._ban_for_proof(miner_hotkey, reason, execution.execution_id)
                self._patch_job_rejected(
                    execution.execution_id,
                    "Invalid private-job proof",
                    execution.execution_data,
                )
            else:
                bt.logging.warning(
                    f"❗ Failed to patch job server for execution_id "
                    f"{execution.execution_id}: {err}"
                )
            return False
        except Exception as e:
            bt.logging.warning(
                f"❗ Failed to patch job server for execution_id "
                f"{execution.execution_id}: {e}"
            )
            return False

    def _patch_execution_status(self, execution_id: str, status: ExecutionStatus) -> bool:
        """Send the request back to the job server with the new status"""
        body: Dict[str, Any] = {
            "status": status,
        }
        return self._patch(execution_id, body)

    @staticmethod
    def _status_value(status: Any) -> str:
        """Jobs ValidationPipe wants Pending|Queued|Running|Completed|Failed."""
        if isinstance(status, ExecutionStatus):
            return status.value
        if isinstance(status, Enum):
            return str(status.value)
        text = str(status)
        if "." in text:
            text = text.rsplit(".", 1)[-1]
        mapping = {
            "PENDING": "Pending",
            "QUEUED": "Queued",
            "RUNNING": "Running",
            "COMPLETED": "Completed",
            "FAILED": "Failed",
        }
        return mapping.get(text.upper(), text)

    def _patch(self, execution_id: str, body: Dict) -> bool:
        """Helper function to patch the job server. Returns True on success."""
        if execution_id == COLLECT_SYNAPSE_ID:
            return True
        bt.logging.debug(f"📌 Patching job server for execution_id {execution_id} with body {body}")
        if self.job_client is None:
            raise ValueError("job_client must be provided to Scorer")
        try:
            payload = dict(body)
            if "status" in payload:
                payload["status"] = self._status_value(payload["status"])
            if "cost" in payload and len(payload) == 2:
                self.job_client.patch_execution_cost(execution_id, float(payload["cost"]))
                return True
            self.job_client.patch_execution(execution_id, payload)
            return True
        except Exception as e:
            bt.logging.warning(f"❗ Failed to patch job server for execution_id {execution_id}: {e}")
            return False

    def _ban_for_proof(
        self,
        miner_hotkey: str | None,
        reason: str,
        execution_id: str | None = None,
    ) -> None:
        if not miner_hotkey:
            return
        try:
            ban_miner(
                self.database_manager,
                miner_hotkey,
                reason,
                hours=PROOF_BAN_HOURS,
            )
        except Exception as err:
            bt.logging.trace(f"ban_miner {reason} failed: {err}")
        self.telemetry_service.vali_record_ban(
            miner_hotkey, reason, PROOF_BAN_HOURS, execution_id
        )
        self.telemetry_service.vali_record_proof_fail(
            miner_hotkey, reason, execution_id
        )

    @staticmethod
    def _proof_error_text(err: Exception) -> str:
        if isinstance(err, JobApiError):
            return (err.platform_message() or str(err)).lower()
        return str(err).lower()

    @classmethod
    def _is_proof_cheat(cls, err: Exception) -> bool:
        text = cls._proof_error_text(err)
        return any(marker in text for marker in _PROOF_CHEAT_MARKERS)

    def _update_last_circuit_table(self, synapse: CircuitSynapse, miner_hotkey: str) -> None:
        """Extract the timestamp of the most recent circuit, store it"""

        try:
            last_update_timestamp = synapse.last_circuit
            query = """
                INSERT OR REPLACE into last_circuit
                (miner_hotkey, timestamp)
                VALUES (?, ?)
            """
            values = (miner_hotkey, last_update_timestamp)
            with self.database_manager.lock:
                self.database_manager.query_and_commit_with_values(query, values)

        # Handle bad data from the miner
        except Exception as e:
            current_thread = threading.current_thread().name
            bt.logging.debug(
                f"| {current_thread} | ❌ Error processing last_circuit timestamp from miner '{miner_hotkey}': {e}")

    def inflight_hotkeys(self) -> set[str]:
        hotkeys = {hk for hk, ids in self._last_active.items() if ids}
        hotkeys.update(hk for hk, _seen in self._inflight_seen.values())
        return hotkeys

    def _save_inflight(
        self,
        execution_id: str,
        miner_hotkey: str,
        seen: float,
        assigned: bool,
    ) -> None:
        if not execution_id or execution_id == COLLECT_SYNAPSE_ID:
            return
        sql = """
            INSERT INTO inflight_execution (execution_id, miner_hotkey, seen_at, assigned)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(execution_id) DO UPDATE SET
                miner_hotkey = excluded.miner_hotkey,
                seen_at = excluded.seen_at,
                assigned = MAX(inflight_execution.assigned, excluded.assigned)
        """
        try:
            with self.database_manager.lock:
                self.database_manager.query_and_commit_with_values(
                    sql,
                    (execution_id, miner_hotkey, float(seen), 1 if assigned else 0),
                )
        except Exception as exc:
            bt.logging.trace(f"inflight persist failed: {exc}")

    def _delete_inflight(self, execution_id: str) -> None:
        if not execution_id:
            return
        try:
            with self.database_manager.lock:
                self.database_manager.query_and_commit_with_values(
                    "DELETE FROM inflight_execution WHERE execution_id = ?",
                    (execution_id,),
                )
        except Exception as exc:
            bt.logging.trace(f"inflight delete failed: {exc}")

    def _load_inflight(self) -> None:
        try:
            with self.database_manager.lock:
                rows = self.database_manager.query(
                    "SELECT execution_id, miner_hotkey, seen_at, assigned FROM inflight_execution"
                )
        except Exception as exc:
            bt.logging.warning(f"inflight load failed: {exc}")
            return
        for execution_id, miner_hotkey, seen_at, assigned in rows or []:
            if not execution_id or execution_id == COLLECT_SYNAPSE_ID:
                continue
            self._inflight_seen[str(execution_id)] = (str(miner_hotkey), float(seen_at))
            if assigned:
                self._assigned.add(str(execution_id))

    def _note_inflight(self, miner_hotkey: str, execution_id: str) -> None:
        if not execution_id or execution_id == COLLECT_SYNAPSE_ID:
            return
        seen = time.time()
        self._inflight_seen[execution_id] = (miner_hotkey, seen)
        self._save_inflight(
            execution_id,
            miner_hotkey,
            seen,
            execution_id in self._assigned,
        )

    def _clear_inflight(self, execution_id: str) -> None:
        self._inflight_seen.pop(execution_id, None)
        self._assigned.discard(execution_id)
        self._delete_inflight(execution_id)

    def _ban_for_lease(self, hotkey: str, execution_id: str) -> None:
        try:
            ban_miner(
                self.database_manager,
                hotkey,
                "lease_expired",
                hours=LEASE_BAN_HOURS,
            )
        except Exception as err:
            bt.logging.trace(f"ban_miner lease_expired failed: {err}")
        self.telemetry_service.vali_record_lease_expired(hotkey, execution_id)
        self.telemetry_service.vali_record_ban(
            hotkey, "lease_expired", LEASE_BAN_HOURS, execution_id
        )
        bt.logging.warning(
            f"Public lease expired for {hotkey[:8]}... execution {execution_id}; "
            f"{int(LEASE_BAN_HOURS)}h local ban"
        )

    def _patch_lease_expired(self, execution_id: str) -> str:
        """Ask Jobs to fail the lease. 'fresh' means another validator heartbeated it."""
        body = {
            "status": ExecutionStatus.FAILED,
            "message": "lease_expired",
            "execution_data": {},
        }
        try:
            payload = dict(body)
            payload["status"] = self._status_value(payload["status"])
            data = self.job_client.patch_execution(execution_id, payload)
        except Exception as err:
            bt.logging.warning(
                f"❗ Failed to patch lease_expired for {execution_id}: {err}"
            )
            return "fresh"
        if not isinstance(data, dict):
            data = {}
        if data.get("reason") == "lease_fresh":
            return "fresh"
        if data.get("updated") is True:
            return "applied"
        if data.get("execution_message") == "lease_expired":
            return "expired"
        return "terminal"

    def expire_stale_leases(
        self,
        now: float | None = None,
        ttl_s: float = PUBLIC_LEASE_SECONDS,
    ) -> int:
        """Local 24h ban when this validator has not seen the execution for the lease TTL.

        Only the validator that sent the work patches Jobs. A patch is ignored
        while any validator's heartbeat is inside the lease, and this tracker
        keeps the execution. Observers ban locally and do not patch.
        """
        now_ts = time.time() if now is None else now
        expired = [
            (eid, hotkey)
            for eid, (hotkey, seen) in list(self._inflight_seen.items())
            if now_ts - seen >= ttl_s
        ]
        n = 0
        for eid, hotkey in expired:
            if eid not in self._assigned:
                self._clear_inflight(eid)
                self._ban_for_lease(hotkey, eid)
                n += 1
                continue
            outcome = self._patch_lease_expired(eid)
            if outcome == "fresh":
                seen = now_ts - ttl_s + 60
                self._inflight_seen[eid] = (hotkey, seen)
                self._save_inflight(eid, hotkey, seen, True)
                continue
            self._clear_inflight(eid)
            if outcome in ("applied", "expired"):
                self._ban_for_lease(hotkey, eid)
                n += 1
        return n

    def _record_execution(self, miner_hotkey: str, execution_id: str, shots: int | None = None) -> None:
        if execution_id and execution_id != COLLECT_SYNAPSE_ID:
            self._assigned.add(execution_id)
        self._note_inflight(miner_hotkey, execution_id)
        self._metrics.insert_job_sent(miner_hotkey, execution_id, shots, timestamp_str())

    def _record_time_received(self, miner_hotkey: str, execution_id: str) -> None:
        self._metrics.update_time_received(miner_hotkey, execution_id, timestamp_str())
