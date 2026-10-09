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

"""
Typed TelemetryService client for Open Quantum.

The client owns its RequestManager.

Recommended:

    telemetry = TelemetryService(
        keypair=wallet.hotkey,
        base_url=telemetry_api_url,
        tensorauth_url=tensorauth_url,
        netuid=netuid,
        node_type="validator",
        network=network,
    )
"""

import time
import bittensor as bt
import numpy as np
from typing import Dict, Any, List, Optional
import queue
import threading

from qbittensor.protocol import COLLECT_SYNAPSE_ID
from qbittensor.utils.request.request_manager import RequestManager
from qbittensor.utils.time import timestamp_iso
from qbittensor.utils.env import get_api_config
from qbittensor.validator.utils.execution_status import ExecutionStatus


class TelemetryService:
    """
    Client for sending telemetry/metrics to the Open Quantum platform.

    Owns its RequestManager.
    """

    def __init__(
        self,
        keypair: Any,
        base_url: str | None = None,
        *,
        tensorauth_url: str | None = None,
        netuid: int | None = None,
        node_type: str = "miner",
        network: str = "",
        export_interval_millis: int = 5000,
        max_queue_size: int = 1000,
        batch_size: int = 10,
    ):
        self.max_queue_size = max_queue_size
        self.batch_size = batch_size
        self.flush_interval = export_interval_millis / 1000.0

        cfg = get_api_config()
        effective_base = base_url or cfg.telemetry_api_url

        self.request_manager = RequestManager(
            keypair,
            node_type=node_type,
            network=network,
            tensorauth_url=tensorauth_url,
            telemetry_api_url=effective_base,
            api_version=cfg.api_version,
            netuid=netuid,
        )

        self.session = self.request_manager._session
        self.queue: queue.Queue[Dict[str, Any]] = queue.Queue(maxsize=max_queue_size)
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._start_background_worker()

    def _to_python_scalar(self, x: Any) -> Any:
        if x is None:
            return None
        if isinstance(x, (int, float, str)):
            return x
        if hasattr(x, "item"):
            return x.item()
        if isinstance(x, (np.integer, np.floating, np.number)):
            return x.item()
        return str(x)

    def _start_background_worker(self):
        def worker():
            while not self._stop_event.is_set():
                try:
                    start_time = time.time()
                    batch: list[Dict[str, Any]] = []
                    while len(batch) < self.batch_size and not self._stop_event.is_set():
                        try:
                            item = self.queue.get(timeout=0.1)
                            batch.append(item)
                        except queue.Empty:
                            break
                    if batch:
                        self._flush_batch(batch)
                    sleep_time = max(0, self.flush_interval - (time.time() - start_time))
                    if sleep_time > 0:
                        self._stop_event.wait(sleep_time)
                except Exception as e:
                    bt.logging.error(f"Background worker error: {e}")
                    time.sleep(1)

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()

    def _format_batch(self, batch: list[Dict[str, Any]]) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []
        for item in batch:
            payload_item: Dict[str, Any] = {
                "type": item["type"],
                "timestamp": item["timestamp"],
            }
            value = item.get("value")
            if isinstance(value, str):
                payload_item["string_value"] = value
            elif value is not None:
                payload_item["numeric_value"] = float(value)
            attributes = item.get("attributes") or {}
            if not isinstance(attributes, dict):
                attributes = {}
            else:
                attributes = dict(attributes)
            # Fold subject miner_hotkey into attributes. The poster identity is the JWT.
            hotkey = item.get("miner_hotkey")
            if hotkey and "miner_hotkey" not in attributes:
                attributes["miner_hotkey"] = hotkey
            if attributes:
                payload_item["attributes"] = attributes
            formatted.append(payload_item)
        return formatted

    def _flush_batch(self, batch: list[Dict[str, Any]]) -> None:
        bt.logging.debug(f"🔭 Flushing batch of {len(batch)} telemetry datapoints")
        datapoints = self._format_batch(batch)
        response = self.request_manager.post_telemetry(
            "datapoints",
            json={"datapoints": datapoints},
        )
        response.raise_for_status()
        for _ in batch:
            self.queue.task_done()

    def _enqueue_datapoint(
        self,
        type: str,
        timestamp: str,
        value: float | str,
        attributes: Optional[Dict[str, Any]] = None,
        miner_hotkey: Optional[str] = None,
    ) -> bool:
        try:
            if self.queue.full():
                bt.logging.warning(f"Queue full (size {self.max_queue_size}); dropping datapoint {type}")
                return False
            safe_value = self._to_python_scalar(value)
            if isinstance(safe_value, (int, float)):
                safe_value = float(safe_value)

            safe_attributes: Dict[str, Any] = {}
            if attributes:
                for k, v in attributes.items():
                    if v is None:
                        continue
                    if isinstance(v, (dict, list, tuple)):
                        safe_attributes[k] = str(v)
                    else:
                        safe_attributes[k] = self._to_python_scalar(v)
            if miner_hotkey and "miner_hotkey" not in safe_attributes:
                safe_attributes["miner_hotkey"] = miner_hotkey

            item = {
                "type": type,
                "timestamp": timestamp,
                "value": safe_value,
                "attributes": safe_attributes or None,
            }
            self.queue.put_nowait(item)
            return True
        except queue.Full:
            bt.logging.warning(f"Queue full; dropping datapoint {type}")
            return False
        except Exception as e:
            bt.logging.debug(f"Failed to enqueue datapoint {type}: {e}")
            return False

    def record_event(
        self,
        type: str,
        value: float | str = 1.0,
        attributes: Optional[Dict[str, Any]] = None,
        miner_hotkey: Optional[str] = None,
    ) -> None:
        try:
            self._enqueue_datapoint(
                type,
                timestamp_iso(),
                value,
                attributes,
                miner_hotkey,
            )
        except Exception as e:
            bt.logging.debug(f"Failed to enqueue {type}: {e}")

    def vali_record_execution_from_jobs_api(self, execution_id: str, miner_hotkey: str):
        try:
            ts = timestamp_iso()
            real = execution_id != COLLECT_SYNAPSE_ID
            self._enqueue_datapoint(
                "vali_execution_from_jobs_api",
                ts,
                1.0 if real else 0.0,
                {"execution_id": execution_id},
                miner_hotkey,
            )
            if real:
                self._enqueue_datapoint(
                    "vali_handout",
                    ts,
                    execution_id,
                    miner_hotkey=miner_hotkey,
                )
        except Exception as e:
            bt.logging.debug(
                f"Failed to enqueue vali_execution_from_jobs_api for miner {miner_hotkey}: {e}"
            )

    def vali_record_execution_from_miner(
            self,
            execution_id: str,
            status: ExecutionStatus,
            miner_hotkey: str):
        try:
            ts = timestamp_iso()
            self._enqueue_datapoint(
                "vali_execution_from_miner",
                ts,
                1.0,
                {
                    "execution_id": execution_id,
                    "status": status.value if isinstance(status, ExecutionStatus) else str(status),
                },
                miner_hotkey,
            )
        except Exception as e:
            bt.logging.debug(
                f"Failed to enqueue vali_execution_from_miner for miner {miner_hotkey}: {e}"
            )

    def vali_record_synapse_response(
        self,
        execution_id: str,
        miner_hotkey: str,
        success: bool,
        rate_limited: Optional[bool] = False,
        error_message: Optional[str] = None,
    ):
        try:
            ts = timestamp_iso()
            self._enqueue_datapoint(
                "vali_record_synapse_response",
                ts,
                1.0,
                {
                    "execution_id": execution_id,
                    "success": success,
                    "rate_limited": rate_limited,
                    "error_message": error_message,
                },
                miner_hotkey,
            )
        except Exception as e:
            bt.logging.debug(
                f"Failed to enqueue vali_record_synapse_response for miner {miner_hotkey}: {e}"
            )

    def vali_record_weights(self, weights: List[float]):
        try:
            ts = timestamp_iso()
            self._enqueue_datapoint("vali_record_weights", ts, 1.0, attributes={"weights": weights})
        except Exception as e:
            bt.logging.debug(f"Failed to enqueue vali_record_weights: {e}")

    def vali_record_heartbeat(self, version: str):
        try:
            ts = timestamp_iso()
            self._enqueue_datapoint("vali_heartbeat", ts, 1.0, attributes={"version": version})
        except Exception as e:
            bt.logging.debug(f"Failed to enqueue heartbeat: {e}")

    def vali_record_ban(
        self,
        miner_hotkey: str,
        reason: str,
        hours: float,
        execution_id: Optional[str] = None,
    ) -> None:
        self.record_event(
            "vali_ban",
            reason,
            {"hours": hours, "execution_id": execution_id or ""},
            miner_hotkey,
        )

    def vali_record_proof_fail(
        self,
        miner_hotkey: str,
        detail: str,
        execution_id: Optional[str] = None,
    ) -> None:
        self.record_event(
            "vali_proof_fail",
            detail,
            {"execution_id": execution_id or ""},
            miner_hotkey,
        )

    def vali_record_lease_expired(
        self,
        miner_hotkey: str,
        execution_id: str,
    ) -> None:
        self.record_event(
            "vali_lease_expired",
            execution_id,
            miner_hotkey=miner_hotkey,
        )

    def vali_record_dropped_inflight(
        self,
        miner_hotkey: str,
        execution_id: str,
    ) -> None:
        self.record_event(
            "vali_dropped_inflight",
            execution_id,
            miner_hotkey=miner_hotkey,
        )

    def vali_record_no_response(
        self,
        miner_hotkey: str,
        execution_id: str,
    ) -> None:
        self.record_event(
            "vali_no_response",
            execution_id,
            miner_hotkey=miner_hotkey,
        )

    def vali_record_axon_backoff(
        self,
        miner_hotkey: str,
        delay_s: float,
    ) -> None:
        self.record_event(
            "vali_axon_backoff",
            float(delay_s),
            {"delay_s": delay_s},
            miner_hotkey,
        )

    def vali_record_rebind(
        self,
        execution_id: str,
        from_hotkey: str,
        to_hotkey: str,
    ) -> None:
        self.record_event(
            "vali_rebind",
            execution_id,
            {"from_hotkey": from_hotkey},
            to_hotkey,
        )

    def vali_record_complete(
        self,
        miner_hotkey: str,
        execution_id: str,
    ) -> None:
        self.record_event(
            "vali_complete",
            execution_id,
            miner_hotkey=miner_hotkey,
        )

    def vali_record_rate_limited(
        self,
        miner_hotkey: str,
        execution_id: str,
    ) -> None:
        self.record_event(
            "vali_rate_limited",
            execution_id,
            miner_hotkey=miner_hotkey,
        )

    def vali_record_miner_failed(
        self,
        miner_hotkey: str,
        execution_id: str,
        message: str,
    ) -> None:
        self.record_event(
            "vali_miner_failed",
            str(message)[:200],
            {"execution_id": execution_id},
            miner_hotkey,
        )

    def miner_record_private_submit(
        self,
        execution_id: str,
        private_job_id: str,
    ) -> None:
        self.record_event(
            "miner_private_submit",
            private_job_id,
            {"execution_id": execution_id},
        )

    def miner_record_private_proof(
        self,
        execution_id: str,
        private_job_id: str,
    ) -> None:
        self.record_event(
            "miner_private_proof",
            private_job_id,
            {"execution_id": execution_id},
        )

    def miner_record_public_upload(self, execution_id: str) -> None:
        self.record_event("miner_public_upload", execution_id)

    def miner_record_submit_fail(self, execution_id: str, reason: str) -> None:
        self.record_event(
            "miner_submit_fail",
            str(reason)[:200],
            {"execution_id": execution_id},
        )

    def miner_record_rate_limited(self, execution_id: str) -> None:
        self.record_event("miner_rate_limited", execution_id)

    def miner_record_execution_received(self, execution_id: str):
        try:
            ts = timestamp_iso()
            self._enqueue_datapoint(
                "miner_execution_received",
                ts,
                execution_id,
            )
        except Exception as e:
            bt.logging.debug(f"Failed to enqueue execution_received: {e}")

    def miner_record_execution_status_change(
        self, execution_id: str, new_status: str, old_status: str
    ):
        try:
            ts = timestamp_iso()
            self._enqueue_datapoint(
                "miner_execution_status_change",
                ts,
                execution_id,
                {"new_status": new_status, "old_status": old_status},
            )
        except Exception as e:
            bt.logging.debug(f"Failed to enqueue execution_status_change: {e}")

    def record_startup_metrics(self):
        try:
            ts = timestamp_iso()
            self._enqueue_datapoint("startup", ts, 1.0)
        except Exception:
            pass

    def shutdown(self):
        try:
            bt.logging.info("Shutting down telemetry service...")
            self._stop_event.set()
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=5.0)
            batch: list[Dict[str, Any]] = []
            while not self.queue.empty():
                try:
                    batch.append(self.queue.get_nowait())
                except queue.Empty:
                    break
            if batch:
                self._flush_batch(batch)
            if hasattr(self, "session"):
                self.session.close()
            bt.logging.info("Telemetry service shutdown complete.")
        except Exception as e:
            bt.logging.warning(f"Error during telemetry shutdown: {e}")


def emit_from_registry(registry: Any, method: str, *args, **kwargs) -> None:
    """Fire a TelemetryService method from a JobRegistry if one was attached."""
    tsvc = getattr(registry, "_telemetry_service", None)
    if tsvc is None:
        return
    fn = getattr(tsvc, method, None)
    if not callable(fn):
        return
    try:
        fn(*args, **kwargs)
    except Exception:
        pass
