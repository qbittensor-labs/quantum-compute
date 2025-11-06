import time
import bittensor as bt
import requests
import numpy as np
from typing import Dict, Any, List, Optional
import queue
import threading

from qbittensor.protocol import COLLECT_SYNAPSE_ID
from qbittensor.utils.request.RequestManager import RequestManager
from qbittensor.utils.timestamping import timestamp_iso
from qbittensor.validator.utils.execution_status import ExecutionStatus

class TelemetryService:
    
    def __init__(self, request_manager: RequestManager, export_interval_millis=5000, max_queue_size=1000, batch_size=10):
        """
        Initialize the TelemetryService.
        Telemetry is disabled if the TELEMETRY_API_URL environment variable is not set or keypair is missing.
        :param request_manager: Bittensor RequestManager for API requests.
        :param node_type: Type of the node (Miner or Validator).
        :param export_interval_millis: Flush interval in ms (for background sending).
        :param network: Deployment network (logged but not used in requests).
        :param max_queue_size: Max size of the internal queue before dropping items.
        :param batch_size: Number of items to batch per send (if API supports; otherwise 1).
        """
        self.max_queue_size = max_queue_size
        self.batch_size = batch_size
        self.flush_interval = export_interval_millis / 1000.0  # Convert to seconds

        self.request_manager = request_manager
        self.session = requests.Session()
        self.queue = queue.Queue(maxsize=max_queue_size)
        self._stop_event = threading.Event()
        self._worker_thread = None
        self._start_background_worker()

    def _to_python_scalar(self, x: Any) -> Any:
        """Convert NumPy or Torch scalars to JSON-serializable Python types."""
        if x is None:
            return None
        if isinstance(x, (int, float, str)):
            return x
        if hasattr(x, 'item'):  # Handles torch.Tensor scalars and NumPy arrays
            return x.item()
        if isinstance(x, (np.integer, np.floating, np.number)):
            return x.item()
        return str(x)  # Fallback for other types

    def _start_background_worker(self):
        """Start the background thread for flushing the queue."""
        def worker():
            while not self._stop_event.is_set():
                try:
                    # Flush every interval or when batch_size reached
                    start_time = time.time()
                    batch = []
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
        """Format a batch of datapoints for the API request."""
        formatted: List[Dict[str, Any]] = []
        for item in batch:
            payload_item = {
                "type": item['type'],
                "timestamp": item['timestamp'],
            }
            if item.get('miner_uid') is not None:
                payload_item["miner_uid"] = item['miner_uid']
            if item.get('miner_hotkey'):
                payload_item["miner_hotkey"] = item['miner_hotkey']
            if isinstance(item['value'], (int, float)):
                payload_item["numeric_value"] = item['value']
            else:
                payload_item["string_value"] = item['value']
            if item.get('attributes'):
                payload_item["attributes"] = item['attributes']
            formatted.append(payload_item)
        return formatted

    def _flush_batch(self, batch: list[Dict[str, Any]]) -> None:
        """Flush a batch of datapoints as a single API request (wrap in 'datapoints' array)."""
        bt.logging.debug(f"🔭 Flushing batch of {len(batch)} telemetry datapoints")
        # Construct batch payload once, send in one request (instead of one-by-one)
        datapoints: List[Dict[str, Any]] = self._format_batch(batch)
        endpoint: str = "datapoints"
        response = self.request_manager.post_telemetry(
            endpoint,
            json={"datapoints": datapoints},
        )
        response.raise_for_status()
        for _ in batch:
            self.queue.task_done()

    def _enqueue_datapoint(self, type: str, timestamp: str, value: float | str, miner_uid: Optional[int] = None, miner_hotkey: Optional[str] = None, attributes: Optional[Dict[str, Any]] = None) -> bool:
        """Enqueue a datapoint; return True if enqueued, False if queue full (dropped)."""
        try:
            if self.queue.full():
                bt.logging.warning(f"Queue full (size {self.max_queue_size}); dropping datapoint {type}")
                return False
            # Convert value to ensure it's a Python scalar (handles NumPy/Torch)
            safe_value = self._to_python_scalar(value)
            if isinstance(safe_value, (int, float)):
                safe_value = float(safe_value)  # Ensure float for numericValue

            # Convert miner_uid
            safe_miner_uid = self._to_python_scalar(miner_uid) if miner_uid is not None else None
            if safe_miner_uid is not None:
                safe_miner_uid = int(safe_miner_uid)

            # Convert attributes values
            safe_attributes = None
            if attributes:
                safe_attributes = {
                    k: self._to_python_scalar(v)
                    for k, v in attributes.items()
                }

            item = {
                'type': type,
                'timestamp': timestamp,
                'value': safe_value,
                'miner_uid': safe_miner_uid,
                'miner_hotkey': miner_hotkey,
                'attributes': safe_attributes,
            }
            self.queue.put_nowait(item)
            return True
        except queue.Full:
            bt.logging.warning(f"Queue full; dropping datapoint {type}")
            return False

    def vali_record_execution_from_jobs_api(self, execution_id: str, miner_uid: int, miner_hotkey: str):
        try:
            timestamp: str = timestamp_iso()
            self._enqueue_datapoint(f"vali_execution_from_jobs_api", timestamp, 0.0 if execution_id == COLLECT_SYNAPSE_ID else 1.0, miner_uid, miner_hotkey, )
        except Exception as e:
            bt.logging.debug(f"Failed to enqueue vali_execution_from_jobs_api for miner {miner_uid}: {e}")  # Non-critical

    def vali_record_execution_from_miner(self, execution_id: str, status: ExecutionStatus, miner_uid: int, miner_hotkey: str):
        try:
            timestamp: str = timestamp_iso()
            self._enqueue_datapoint(f"vali_execution_from_miner", timestamp, 1.0, miner_uid, miner_hotkey, {"execution_id": execution_id, "status": status})
        except Exception as e:
            bt.logging.debug(f"Failed to enqueue vali_execution_from_miner for miner {miner_uid}: {e}")  # Non-critical

    def vali_record_synapse_response(self, execution_id: str, miner_uid: int, miner_hotkey: str, success: bool, rate_limited: Optional[bool] = False, error_message: Optional[str] = None):
        try:
            timestamp: str = timestamp_iso()
            self._enqueue_datapoint(f"vali_record_synapse_response", timestamp, 1.0, miner_uid, miner_hotkey, {"execution_id": execution_id, "success": success, "rate_limited": rate_limited, "error_message": error_message})
        except Exception as e:
            bt.logging.debug(f"Failed to enqueue vali_record_synapse_response for miner {miner_uid}: {e}")  # Non-critical

    def vali_record_weights(self, weights: List[float]):
        try:
            timestamp: str = timestamp_iso()
            self._enqueue_datapoint(f"vali_record_weights", timestamp, 1.0, attributes={"weights": weights})
        except Exception as e:
            bt.logging.debug(f"Failed to enqueue vali_record_weights: {e}")  # Non-critical

    def vali_record_heartbeat(self, version: str):
        try:
            timestamp: str = timestamp_iso()
            # Record version as string
            self._enqueue_datapoint("heartbeat_version", timestamp, version)
        except Exception as e:
            bt.logging.debug(f"Failed to enqueue heartbeat: {e}")

    def miner_record_execution_received(self, execution_id: str, miner_uid: int, miner_hotkey: str):
        try:
            timestamp: str = timestamp_iso()
            self._enqueue_datapoint(f"miner_execution_received", timestamp, 0.0 if execution_id == COLLECT_SYNAPSE_ID else 1, miner_uid, miner_hotkey)
        except Exception as e:
            bt.logging.debug(f"Failed to enqueue execution_received for miner {miner_uid}: {e}")  # Non-critical

    def miner_record_execution_status_change(self, execution_id: str, new_status: str, old_status, miner_uid: int, miner_hotkey: str):
        try:
            timestamp: str = timestamp_iso()
            self._enqueue_datapoint(f"miner_execution_status_change", timestamp, execution_id, miner_uid, miner_hotkey, {"new_status": new_status, "old_status": old_status})
        except Exception as e:
            bt.logging.debug(f"Failed to enqueue execution_status_change for miner {miner_uid}: {e}")  # Non-critical

    def shutdown(self):
        """
        Shuts down the requests session and flushes the queue.
        This should be called during application cleanup.
        """
        try:
            bt.logging.info("Shutting down metrics service...")
            self._stop_event.set()
            if self._worker_thread:
                self._worker_thread.join(timeout=5.0)  # Wait up to 5s for flush
            # Force flush remaining
            batch = []
            while not self.queue.empty():
                try:
                    batch.append(self.queue.get_nowait())
                except queue.Empty:
                    break
            if batch:
                self._flush_batch(batch)
            self.session.close()
            bt.logging.info("Metrics service shutdown complete. ✅")
        except Exception as e:
            bt.logging.warning(f"Error during shutdown: {e}")