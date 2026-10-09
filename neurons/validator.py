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
from typing import Any, List
import numpy as np
import bittensor as bt

from qbittensor.database.database_manager import DatabaseManager
from qbittensor.protocol import COLLECT_SYNAPSE_ID
from qbittensor.validator.heartbeat import Heartbeat
from qbittensor.validator.miner_manager.capabilities import (
    get_placeable_classes,
    upsert_capabilities,
)
from qbittensor.validator.miner_manager.miner_manager import MinerManager
from qbittensor.utils.services import JobClient, TelemetryService
from qbittensor.utils.env import env_csv, get_api_config, load_env
from qbittensor.utils.shutdown import install_shutdown
from qbittensor.validator.miner_manager.next_miner import BasicMiner, NextMiner
from qbittensor.base.validator import BaseValidatorNeuron
from qbittensor.validator.compute_request.compute_request import ComputeRequest
from qbittensor.validator.reward.score import Scorer
from qbittensor.validator.synapse.synapse_manager import SynapseManager
from qbittensor.validator.weights.epoch import has_unpriced_cost
from qbittensor.validator.weights.weight_setter import WeightSetter

load_env()


class Validator(BaseValidatorNeuron):

    def __init__(self, config=None):
        # Set before super().__init__; its sync() calls set_weights.
        self.weight_setter = None
        self._planned_weight_epoch = None
        self._last_weight_epoch_id = None
        super(Validator, self).__init__(config=config)

        my_hotkey = self.wallet.hotkey.ss58_address
        self.database_manager = DatabaseManager(f"validator_{my_hotkey}")
        database_manager = self.database_manager

        cfg = get_api_config()
        self.job_client = JobClient(
            keypair=self.wallet.hotkey,
            base_url=cfg.job_api_url,
            tensorauth_url=cfg.tensorauth_url,
            api_version=cfg.api_version,
            node_type="validator",
            network=self.subtensor.network,
            netuid=self.config.netuid,
        )
        self.telemetry_service = TelemetryService(
            keypair=self.wallet.hotkey,
            base_url=cfg.telemetry_api_url,
            tensorauth_url=cfg.tensorauth_url,
            netuid=self.config.netuid,
            node_type="validator",
            network=self.subtensor.network,
        )
        self.telemetry_service.record_startup_metrics()

        self.synapse_manager = SynapseManager(
            database_manager,
            telemetry_service=self.telemetry_service,
            job_client=self.job_client,
        )
        self.scorer = Scorer(
            database_manager,
            self.metagraph,
            telemetry_service=self.telemetry_service,
            job_client=self.job_client)
        self.next_miner = NextMiner(
            self.metagraph,
            skip_hotkeys={
                self.wallet.hotkey.ss58_address,
                *([str(self.metagraph.owner_hotkey)] if getattr(self.metagraph, "owner_hotkey", None) else []),
            },
        )

        self.miner_manager = MinerManager(database_manager, self.metagraph)

        # Snapshot math. Chain submission goes through base set_weights.
        self.weight_setter = WeightSetter(
            self.metagraph,
            telemetry_service=self.telemetry_service,
        )

        self.heartbeat = Heartbeat(telemetry_service=self.telemetry_service)

    def forward(self):
        # These timers only advance when forward runs.
        self.heartbeat.timer.check_timer()
        self.miner_manager.timer.check_timer()

        current_thread = threading.current_thread().name
        bt.logging.info(f"| {current_thread} | ⏩ Running forward pass")

        answered = self._sweep_running_jobs(current_thread)
        self.scorer.expire_stale_leases()
        self._forward_class_claim(current_thread, answered)

    def _forward_class_claim(
        self, current_thread: str, answered: set[str] | None = None
    ) -> None:
        """Class-claim for one miner who answered this sweep. Empty placeable set collects only."""
        db = getattr(self, "database_manager", None)
        cached = get_placeable_classes(db) if db is not None else {}
        allowlist = env_csv("PUBLIC_BACKEND_CLASSES")
        allow = set(allowlist) if allowlist else None

        if cached:
            union: set[str] = set()
            for classes in cached.values():
                union.update(classes)
            placeable = [c for c in union if allow is None or c in allow]
        else:
            placeable = list(allowlist)

        if not placeable:
            bt.logging.info(
                f"| {current_thread} | 📭 No placeable classes; collect-only"
            )
            self._report_spark([])
            self._collect_only_probe(current_thread)
            return

        reached = answered or set()
        if not reached:
            bt.logging.info(
                f"| {current_thread} | 📭 No miner answered this sweep; collect-only"
            )
            self._report_spark([])
            self._collect_only_probe(current_thread)
            return

        miner = None
        claim_classes: list[str] = []
        if cached and db is not None:
            try:
                miner = self.next_miner.get_next_miner_for_class(
                    None, db, only_hotkeys=reached
                )
            except IndexError:
                miner = None
            if miner is not None:
                caps = list(cached.get(miner.hotkey) or [])
                claim_classes = [c for c in caps if allow is None or c in allow]
                if not claim_classes and allowlist:
                    claim_classes = list(allowlist)
        else:
            try:
                miner = self.next_miner.get_next_miner(only_hotkeys=reached)
            except IndexError:
                miner = None
            claim_classes = list(allowlist) if allowlist else list(placeable)

        if miner is None or not claim_classes:
            bt.logging.info(
                f"| {current_thread} | 📭 No serving miner for class-claim; collect-only"
            )
            self._report_spark([])
            self._collect_only_probe(current_thread)
            return

        synapse, original_compute_request = None, None
        try:
            synapse, original_compute_request = self.synapse_manager.get_synapse_for_classes(
                claim_classes, actor_id=miner.hotkey, miner=miner
            )
        except Exception as err:
            bt.logging.warning(
                f"| {current_thread} | ❌ Class-claim GET failed: {type(err).__name__}: {err}"
            )
        self._report_spark(claim_classes)

        if (
            synapse is None
            or original_compute_request is None
            or original_compute_request.execution_id == COLLECT_SYNAPSE_ID
        ):
            bt.logging.info(
                f"| {current_thread} | 📭 Class-claim 204/empty for miner '{miner.hotkey}'"
            )
            return

        bt.logging.info(f"| {current_thread} | 🔗  Class-claim miner '{miner}'")
        self._query_and_score(miner, synapse, original_compute_request)

    def _sweep_running_jobs(self, current_thread: str) -> set[str]:
        """Collect from serving axons. Returns hotkeys willing to take new work.

        A miner who answers with rate_limited is still collected, so in-flight
        work heartbeats, and is left out of class-claim.
        """
        willing: set[str] = set()
        db = getattr(self, "database_manager", None)
        miners = self.next_miner.list_serving_miners(
            db, heartbeat_hotkeys=self._inflight_hotkeys()
        )
        if not miners:
            bt.logging.trace(f"| {current_thread} | ⏭️  Sweep: no serving miners")
            return willing
        synapse, compute = self.synapse_manager.collect_only_synapse(miners[0])
        axons = [m.axon for m in miners]
        try:
            responses = self.dendrite.query(
                axons=axons,
                synapse=synapse,
                deserialize=True,
                timeout=10,
            )
        except Exception as err:
            bt.logging.warning(
                f"| {current_thread} | ❌ Sweep dendrite failed: {type(err).__name__}: {err}"
            )
            for miner in miners:
                self._note_dendrite_fail(miner)
            return willing
        if responses is None:
            responses = []
        if not isinstance(responses, list):
            responses = [responses]
        while len(responses) < len(miners):
            responses.append(None)
        for miner, resp in zip(miners, responses):
            success = True
            if resp is None:
                success = False
            else:
                dstat = getattr(getattr(resp, "dendrite", None), "status_code", None)
                if dstat not in (None, 200, "200"):
                    success = False
                if getattr(resp, "success", True) is False:
                    success = False
            if not success:
                self._note_dendrite_fail(miner)
                continue
            self.next_miner.record_success(miner.hotkey)
            if getattr(resp, "rate_limited", False) is not True:
                willing.add(miner.hotkey)
            self._upsert_capabilities_from_responses(
                resp if isinstance(resp, list) else [resp], miner
            )
            self.scorer.process_miner_responses(
                resp if isinstance(resp, list) else [resp],
                miner,
                compute,
            )
        return willing

    def _collect_only_probe(self, current_thread: str, miner: BasicMiner | None = None) -> None:
        if miner is None:
            try:
                miner = self.next_miner.get_next_miner()
            except IndexError:
                miner = None
        if miner is None:
            bt.logging.trace(f"| {current_thread} | ⏭️  Collect-only: no serving miner")
            return
        synapse, compute = self.synapse_manager.collect_only_synapse(miner)
        self._query_and_score(miner, synapse, compute)

    def _report_spark(self, classes: list[str]) -> None:
        if not classes:
            return
        try:
            self.job_client.report_spark(classes)
        except Exception as err:
            bt.logging.trace(f"spark/report failed: {type(err).__name__}: {err}")

    def _query_and_score(
        self,
        next_miner: BasicMiner,
        synapse: Any,
        original_compute_request: ComputeRequest,
        *,
        allow_rebind: bool = True,
    ) -> None:
        current_thread = threading.current_thread().name
        try:
            response: List[Any] = self.dendrite.query(
                axons=[next_miner.axon],
                synapse=synapse,
                deserialize=True,
                timeout=10
            )
        except Exception as err:
            self._note_dendrite_fail(next_miner, original_compute_request.execution_id)
            bt.logging.warning(
                f"| {current_thread} | ❌ Dendrite query to miner '{next_miner}' failed: "
                f"{type(err).__name__}: {err}"
            )
            if allow_rebind:
                self._retry_claimed_execution(next_miner, synapse, original_compute_request)
            else:
                self.scorer._patch_job_rejected(
                    original_compute_request.execution_id, "Miner did not respond"
                )
            return

        if response is None:
            self._note_dendrite_fail(next_miner, original_compute_request.execution_id)
            bt.logging.info(f"| {current_thread} | ❗ No responses from miner '{next_miner}'.")
            if allow_rebind:
                self._retry_claimed_execution(next_miner, synapse, original_compute_request)
            else:
                self.scorer._patch_job_rejected(
                    original_compute_request.execution_id, "Miner did not respond"
                )
            return

        self.next_miner.record_success(next_miner.hotkey)
        self._upsert_capabilities_from_responses(response, next_miner)
        self.scorer.process_miner_responses(response, next_miner, original_compute_request)

    def _retry_claimed_execution(
        self,
        failed_miner: BasicMiner,
        synapse: Any,
        original_compute_request: ComputeRequest,
    ) -> None:
        """In-round: rebind a still-Pending claim to another miner before failing to the cloud."""
        if original_compute_request.execution_id == COLLECT_SYNAPSE_ID:
            return
        try:
            alt = self.next_miner.get_next_miner()
        except IndexError:
            alt = None
        if alt is None or alt.hotkey == failed_miner.hotkey:
            self.scorer._patch_job_rejected(
                original_compute_request.execution_id,
                "Miner did not respond",
            )
            return
        try:
            self.job_client.patch_execution(
                original_compute_request.execution_id,
                {"status": "Pending", "miner_hotkey": alt.hotkey},
            )
        except Exception as err:
            bt.logging.trace(f"rebind patch failed: {type(err).__name__}: {err}")
            self.scorer._patch_job_rejected(
                original_compute_request.execution_id,
                "Miner did not respond",
            )
            return
        bt.logging.info(
            f"Rebinding execution {original_compute_request.execution_id} "
            f"from {failed_miner.hotkey} to {alt.hotkey}"
        )
        try:
            self.telemetry_service.vali_record_rebind(
                original_compute_request.execution_id,
                failed_miner.hotkey,
                alt.hotkey,
            )
        except Exception:
            pass
        self._query_and_score(alt, synapse, original_compute_request, allow_rebind=False)

    def _inflight_hotkeys(self) -> set[str]:
        scorer = getattr(self, "scorer", None)
        if scorer is None or not hasattr(scorer, "inflight_hotkeys"):
            return set()
        try:
            return set(scorer.inflight_hotkeys())
        except Exception:
            return set()

    def _note_dendrite_fail(
        self,
        miner: BasicMiner,
        execution_id: str | None = None,
    ) -> None:
        delay = self.next_miner.record_timeout(
            miner.hotkey, inflight=miner.hotkey in self._inflight_hotkeys()
        )
        tel = getattr(self, "telemetry_service", None)
        if tel is None:
            return
        try:
            if delay is not None:
                tel.vali_record_axon_backoff(miner.hotkey, delay)
            if execution_id and execution_id != COLLECT_SYNAPSE_ID:
                tel.vali_record_no_response(miner.hotkey, execution_id)
        except Exception:
            pass

    def _upsert_capabilities_from_responses(self, response: Any, miner: BasicMiner) -> None:
        db = getattr(self, "database_manager", None)
        if db is None:
            return
        synapses = response if isinstance(response, list) else [response]
        for syn in synapses:
            # A failed dendrite still carries capabilities=[]. Caching that skips the axon forever.
            if not getattr(syn, "success", False):
                continue
            caps = getattr(syn, "capabilities", None)
            if caps is None:
                continue
            try:
                upsert_capabilities(db, miner.hotkey, list(caps))
            except Exception as err:
                bt.logging.trace(f"capability upsert failed: {type(err).__name__}: {err}")

    def _weights_rate_limit(self) -> int:
        try:
            hp = getattr(self.subtensor, "hyperparameters", None)
            for name in ("weights_rate_limit", "weights_set_rate_limit"):
                fn = getattr(hp, name, None)
                if callable(fn):
                    val = fn(netuid=self.config.netuid)
                else:
                    val = fn
                if isinstance(val, int) and val > 0:
                    return val
        except Exception:
            pass
        return 100

    def should_set_weights(self) -> bool:
        """Commit when the platform epoch snapshot changes (not local block//tempo)."""
        if self.step == 0:
            return False
        if getattr(self.config.neuron, "disable_set_weights", False):
            return False
        job_client = getattr(self, "job_client", None)
        if job_client is None:
            return False
        try:
            snap = job_client.get_weight_epoch()
        except Exception as exc:
            bt.logging.debug(f"weight epoch unavailable: {exc}")
            return False
        epoch_id = snap.get("epoch_id")
        if epoch_id is None:
            return False
        if has_unpriced_cost(snap):
            bt.logging.warning(
                f"Weight epoch {epoch_id} skipped; prices are missing "
                "and the cost book is present"
            )
            return False
        if epoch_id == self._last_weight_epoch_id:
            return False
        try:
            elapsed = int(self.block) - int(self.metagraph.last_update[self.uid])
        except Exception:
            elapsed = None
        rate = self._weights_rate_limit()
        if elapsed is not None and elapsed < rate:
            bt.logging.info(
                f"Weight epoch {epoch_id} pending; waiting for weights_rate_limit "
                f"({elapsed}/{rate} blocks)."
            )
            return False
        self._planned_weight_epoch = snap
        return True

    def _mark_local_weights_submitted(self) -> None:
        super()._mark_local_weights_submitted()
        snap = self._planned_weight_epoch
        if isinstance(snap, dict) and snap.get("epoch_id") is not None:
            self._last_weight_epoch_id = snap.get("epoch_id")
            bt.logging.info(
                f"Recorded weight epoch {self._last_weight_epoch_id} "
                f"hash={snap.get('payload_hash')}"
            )
        self._planned_weight_epoch = None

    def set_weights(self):
        """Weights from the frozen Jobs epoch snapshot, then on-chain SetWeights."""
        try:
            if self.weight_setter is None:
                bt.logging.warning("No weight_setter; skipping weight computation")
                return
            snap = self._planned_weight_epoch
            if not isinstance(snap, dict):
                snap = self.job_client.get_weight_epoch()
                self._planned_weight_epoch = snap
            weights_list = self.weight_setter.weights_from_snapshot(snap)
            if weights_list is None:
                if has_unpriced_cost(snap):
                    bt.logging.warning(
                        "Skipping set_weights: prices are missing and the cost book is present"
                    )
                else:
                    bt.logging.warning(
                        "Skipping set_weights: required hotkey is not on the metagraph"
                    )
                self._planned_weight_epoch = None
                return

            n = int(getattr(self.metagraph, "n", len(weights_list)))
            scores = np.zeros(n, dtype=np.float32)
            for uid in range(min(len(weights_list), n)):
                scores[uid] = float(weights_list[uid])

            try:
                self.weight_setter.telemetry_service.vali_record_weights(
                    [float(w) for w in weights_list]
                )
            except Exception:
                pass
            non_zero = [(u, w) for u, w in enumerate(weights_list) if w > 0]
            if non_zero:
                bt.logging.info(f"Non-zero miner weights: {non_zero}")
            bt.logging.info(
                f"🔢 Weight epoch {snap.get('epoch_id')} "
                f"hash={snap.get('payload_hash')}"
            )
            self.scores = scores
            super().set_weights()
        except Exception as exc:
            if "NeuronNoValidatorPermit" in str(exc):
                bt.logging.warning("⚠️ No validator permit")
            else:
                bt.logging.error(f"❌ Weight-setting error: {exc}")

    def save_state(self):
        """No-op. State is recomputed from the database."""
        pass

    def load_state(self):
        """No-op. State is recomputed from the database."""
        pass


# The main function parses the configuration and runs the validator.
if __name__ == "__main__":
    validator = Validator()
    install_shutdown(validator)
    with validator:
        while (
            not validator.should_exit
            and validator.is_running
            and validator.thread
            and validator.thread.is_alive()
        ):
            time.sleep(1)
        if not validator.should_exit:
            bt.logging.warning("Validator background thread has stopped. Exiting.")
