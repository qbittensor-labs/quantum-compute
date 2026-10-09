# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
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
import typing
import bittensor as bt
from typing import List, Tuple
from types import SimpleNamespace
import requests

from qbittensor.database.database_manager import DatabaseManager

# Base miner class which takes care of most of the boilerplate
from qbittensor.base.miner import BaseMinerNeuron
from qbittensor.protocol import COLLECT_SYNAPSE_ID, CircuitSynapse, ExecutionData
from qbittensor.miner.runtime.registry import JobRegistry
from qbittensor.utils.services import JobClient, TelemetryService
from qbittensor.utils.env import get_api_config, load_env
from qbittensor.utils.shutdown import install_shutdown

from qbittensor.constants import COMPLETED_CIRCUIT_TTL

load_env()


def _has_validator_permit(metagraph, uid: int) -> bool:
    """False when the permit bit is missing or unset."""
    permits = getattr(metagraph, "validator_permit", None)
    if isinstance(permits, (list, tuple)):
        return 0 <= uid < len(permits) and bool(permits[uid])
    shape = getattr(permits, "shape", None)
    if isinstance(shape, tuple) and shape:
        try:
            return bool(permits[uid])
        except (IndexError, TypeError, ValueError):
            return False
    return False


class Miner(BaseMinerNeuron):

    def __init__(self, config=None):
        super(Miner, self).__init__(config=config)
        my_hotkey = self.wallet.hotkey.ss58_address
        self.database_manager = DatabaseManager(f"miner_{my_hotkey}")
        cfg = get_api_config()
        self.job_client = JobClient(
            keypair=self.wallet.hotkey,
            base_url=cfg.job_api_url,
            tensorauth_url=cfg.tensorauth_url,
            api_version=cfg.api_version,
            node_type="miner",
            network=self.subtensor.network,
            netuid=self.config.netuid,
        )
        self.telemetry_service = TelemetryService(
            keypair=self.wallet.hotkey,
            base_url=cfg.telemetry_api_url,
            tensorauth_url=cfg.tensorauth_url,
            netuid=self.config.netuid,
            node_type="miner",
            network=self.subtensor.network,
        )
        self.telemetry_service.record_startup_metrics()
        self.jobs = JobRegistry(self.database_manager, self.wallet.hotkey, job_client=self.job_client)
        try:
            setattr(self.jobs, "_telemetry_service", self.telemetry_service)
        except Exception:
            pass
        try:
            self.jobs.restore_open_executions()
            if self.jobs._jobs:
                self.jobs.start()
        except Exception as exc:
            bt.logging.error(f"Failed to restore open executions: {exc}")

    def forward(self, synapse: CircuitSynapse) -> CircuitSynapse:
        synapse.capabilities = self._list_public_classes()
        self.telemetry_service.miner_record_execution_received(synapse.execution_id)

        current_thread = threading.current_thread().name

        validator_hotkey = self._get_validator_hotkey(synapse)
        if validator_hotkey is None:
            bt.logging.trace(f"| {current_thread} | ❗ Failed to extract validator hotkey")
            return synapse

        bt.logging.trace(f"| {current_thread} | 🚚 Received synapse from validator '{validator_hotkey}'")

        # Finished rows go out before submit so the dendrite is not waiting on a download.
        self._update_synapse_with_finished_executions(synapse)
        self._drop_old_circuit_data()

        if synapse.execution_id == COLLECT_SYNAPSE_ID:
            bt.logging.trace(
                f"| {current_thread} | 📬 Received collect-only request from validator '{validator_hotkey}'")
            self._mark_low_credits(synapse)
            return synapse

        if self._rate_limit():
            bt.logging.trace(f"| {current_thread} | 🚧 Rate limiting this request")
            synapse.rate_limited = True
            try:
                self.telemetry_service.miner_record_rate_limited(synapse.execution_id)
            except Exception:
                pass
            return synapse

        if self._job_is_new(synapse.execution_id):
            if self._mark_low_credits(synapse):
                return synapse

            # Submit off the axon thread. A slow download must not be scored as no response.
            def _bg_submit():
                try:
                    response = requests.get(synapse.input_data_url, timeout=5)
                    response.raise_for_status()
                    cfg = synapse.configuration_data if isinstance(synapse.configuration_data, dict) else {}
                    raw_shots = cfg.get("shots") if isinstance(cfg, dict) else None
                    try:
                        shots = int(raw_shots) if raw_shots is not None else None
                    except (TypeError, ValueError):
                        shots = None
                    self.jobs.submit(
                        execution_id=synapse.execution_id,
                        input_data_url=synapse.input_data_url,
                        validator_hotkey=validator_hotkey,
                        shots=shots,
                        configuration_data=cfg,
                        backend_class_id=synapse.backend_class_id,
                    )
                except Exception as e:
                    bt.logging.debug(f"❌ Submit failed for execution {synapse.execution_id}: {e}")
                    try:
                        self.telemetry_service.miner_record_submit_fail(
                            synapse.execution_id,
                            str(e),
                        )
                    except Exception:
                        pass
                    # Persist the failure for the next collect.
                    try:
                        from qbittensor.miner.runtime.repository import persist_failed
                        persist_failed(
                            self.jobs,
                            execution_id=synapse.execution_id,
                            validator_hotkey=validator_hotkey,
                            provider=None,
                            provider_job_id=None,
                            device_id=None,
                            error_message=f"Provider submit failed: {e}",
                            metadata=None,
                        )
                    except Exception:
                        pass

            self.jobs.spawn_submit(
                _bg_submit,
                name=f"bg-submit-{synapse.execution_id[:8]}",
            )

        return synapse

    def _list_public_classes(self) -> List[str]:
        """Classes this miner accepts. Empty means not placeable."""
        adapter = getattr(getattr(self, "jobs", None), "adapter", None)
        if adapter is not None and hasattr(adapter, "list_public_classes"):
            try:
                classes = adapter.list_public_classes()
                if classes is not None:
                    return [str(c) for c in classes]
            except Exception:
                pass
        from qbittensor.miner.providers.base import list_public_classes_from_env
        return list_public_classes_from_env()

    def _rate_limit(self) -> bool:
        """Unused. Credit checks set synapse.rate_limited directly."""
        return False

    def _mark_low_credits(self, synapse: CircuitSynapse) -> bool:
        """Set rate_limited when the credit balance is under the floor. Finished rows stay on the synapse."""
        try:
            adapter = getattr(self.jobs, "adapter", None)
            should_rl = getattr(adapter, "should_rate_limit_request", None)
            if not callable(should_rl) or should_rl(shots=synapse.shots) is not True:
                return False
        except Exception:
            return False
        bt.logging.trace(
            f"| {threading.current_thread().name} | Provider requested per-request rate limit (low credits)"
        )
        synapse.rate_limited = True
        try:
            self.telemetry_service.miner_record_rate_limited(synapse.execution_id)
        except Exception:
            pass
        return True

    def _update_synapse_with_finished_executions(self, synapse: CircuitSynapse) -> None:
        current_thread = threading.current_thread().name

        last_update = synapse.last_circuit
        finished_executions, last_circuit = self._get_finished_executions(last_update)
        bt.logging.trace(f"| {current_thread} | 📋 Found {len(finished_executions)} finished jobs")

        synapse.finished_executions.extend(finished_executions)
        synapse.active_executions = self._get_active_executions()
        synapse.last_circuit = last_circuit
        synapse.success = True

    def _get_finished_executions(self, last_update: str) -> Tuple[List[ExecutionData], str]:
        """Terminal rows after this validator's watermark.

        Each validator keeps its own watermark. Rows older than
        COMPLETED_CIRCUIT_TTL days are pruned.
        """

        if not last_update:
            last_update = "1970-01-01 00:00:00"
        query = """
            SELECT execution_id, COALESCE(shots, 0) as shots, upload_data_id, provider_job_id,
                   status, errorMessage, timestamp, metadata_json
            FROM executions
            WHERE timestamp > ? AND status != 'Running'
        """
        values = (last_update,)
        with self.database_manager.lock:
            results = self.database_manager.query_with_values(query, values)

        finished_executions = []
        timestamps = []
        for row in results:
            execution_id, shots, upload_data_id, provider_job_id, status, errorMessage, ts, metadata_json = (
                row + (None,) * (8 - len(row))
            )[:8]
            extra: dict = {"provider_job_id": provider_job_id}
            if metadata_json:
                try:
                    import json as _json
                    meta = _json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
                    if isinstance(meta, dict):
                        extra.update(meta)
                        extra.pop("dry_run", None)
                except Exception:
                    pass
            finished_executions.append(
                ExecutionData(
                    execution_id=execution_id,
                    shots=shots,
                    upload_data_id=upload_data_id,
                    execution_data=extra,
                    status=status,
                    errorMessage=errorMessage,
                )
            )
            timestamps.append(ts)

        # Get the most recent timestamp. If no data came back from query, default
        # this to the same timestamp the validator sent.
        most_recent_timestamp = last_update
        if len(timestamps) > 0:
            most_recent_timestamp = max(timestamps)

        # Return a tuple
        return finished_executions, most_recent_timestamp

    def _drop_old_circuit_data(self) -> None:
        """Drop any data from executions table older than n days"""
        query = f"""
            DELETE FROM executions
            WHERE timestamp < date('now', '-{COMPLETED_CIRCUIT_TTL} days')
        """
        with self.database_manager.lock:
            self.database_manager.query_and_commit(query)

    def _get_active_executions(self) -> List[ExecutionData]:
        query = """
            SELECT execution_id, COALESCE(shots, 0) as shots, upload_data_id, provider_job_id,
                   status, errorMessage
            FROM executions
            WHERE status IN ('Pending', 'Queued', 'Running')
        """
        with self.database_manager.lock:
            results = self.database_manager.query(query)
        active: List[ExecutionData] = []
        for row in results or []:
            execution_id, shots, upload_data_id, provider_job_id, status, errorMessage = row[:6]
            active.append(
                ExecutionData(
                    execution_id=execution_id,
                    shots=shots,
                    upload_data_id=upload_data_id,
                    execution_data={"provider_job_id": provider_job_id},
                    status=status,
                    errorMessage=errorMessage,
                )
            )
        return active

    def _job_is_new(self, execution_id: str) -> bool:
        """Check if this request id has been seen yet"""
        try:
            if hasattr(self, "jobs") and self.jobs.is_tracking(execution_id):
                return False
        except Exception:
            pass
        table = "executions"
        conditions = "execution_id=?"
        values = (execution_id,)
        with self.database_manager.lock:
            return not self.database_manager.row_exists(table, conditions, values)

    def _get_validator_hotkey(self, synapse: CircuitSynapse) -> str | None:
        """Return the validator hotkey for this synapse"""
        if not synapse.dendrite:
            return None
        return synapse.dendrite.hotkey

    async def blacklist(self, synapse: CircuitSynapse) -> typing.Tuple[bool, str]:
        if not synapse.dendrite or synapse.dendrite.hotkey not in self.metagraph.hotkeys:
            validator_hotkey = synapse.dendrite.hotkey if synapse.dendrite else "UNKNOWN"
            bt.logging.info(f"❗Blacklisted unknown hotkey: {validator_hotkey}")
            return True, f"❗Hotkey {validator_hotkey} was not found from metagraph.hotkeys",

        stake, uid = self.get_validator_stake_and_uid(synapse.dendrite.hotkey)

        if getattr(getattr(self.config, "blacklist", None), "force_validator_permit", False):
            if not _has_validator_permit(self.metagraph, uid):
                bt.logging.info(
                    f"❗Blacklisted hotkey {synapse.dendrite.hotkey} without a validator permit"
                )
                return (
                    True,
                    f"❗Hotkey {synapse.dendrite.hotkey} does not have a validator permit",
                )

        validator_min_stake = 0.0
        if stake < validator_min_stake:
            bt.logging.info(f"❗Blacklisted validator {synapse.dendrite.hotkey} with insufficient stake: {stake}")
            return True, f"❗Hotkey {synapse.dendrite.hotkey} has insufficient stake: {stake}",

        bt.logging.info(f"✅ Accepted hotkey: {synapse.dendrite.hotkey} (UID: {uid} - Stake: {stake})")
        return False, f"✅ Accepted hotkey: {synapse.dendrite.hotkey}"

    async def priority(self, synapse: CircuitSynapse) -> float:
        """Priority function determines order in which requests are handled"""
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning(
                "Received a request without a dendrite or hotkey."
            )
            return 0.0

        bt.logging.debug(f"🧮 Calculating priority for synapse from {synapse.dendrite.hotkey}")
        stake, uid = self.get_validator_stake_and_uid(synapse.dendrite.hotkey)
        bt.logging.debug(f"🏆 Prioritized: {synapse.dendrite.hotkey} (UID: {uid} - Stake: {stake})")
        return stake

    def get_validator_stake_and_uid(self, hotkey):
        uid = self.metagraph.hotkeys.index(hotkey)
        return float(self.metagraph.S[uid]), uid

    def resync_metagraph(self):
        """Resync metagraph (override to avoid extra logs if desired)."""
        self.metagraph.sync(subtensor=self.subtensor)

    def save_state(self):
        """No-op. Miner state lives in the local database."""
        pass

    def load_state(self):
        """No-op. Miner state lives in the local database."""
        pass

    @classmethod
    def config(cls):
        return cls._apply_secure_blacklist_defaults(super().config())

    @classmethod
    def _apply_secure_blacklist_defaults(cls, config: "bt.Config") -> "bt.Config":
        """Only registered hotkeys with a validator permit may query."""
        if not hasattr(config, "blacklist") or config.blacklist is None:
            config.blacklist = bt.Config()
        if getattr(config, "blacklist", None) is None:
            config.blacklist = SimpleNamespace()

        config.blacklist.allow_non_registered = False
        config.blacklist.force_validator_permit = True
        return config


# This is the main function, which runs the miner.
if __name__ == "__main__":
    miner = Miner()
    install_shutdown(miner, miner.jobs.request_stop)
    try:
        with miner:
            miner.jobs.start()
            while (
                not miner.should_exit
                and miner.is_running
                and miner.thread
                and miner.thread.is_alive()
            ):
                time.sleep(1)
    finally:
        miner.should_exit = True
        miner.jobs.join_submits(15)
        miner.jobs.stop()
