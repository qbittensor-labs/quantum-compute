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

import json
import threading
import bittensor as bt
import time
from datetime import timedelta
import queue
from typing import Callable, Dict, Optional
import requests
import os


from qbittensor.database.database_manager import DatabaseManager
from qbittensor.miner.providers.base import Capabilities, JobHandle, MinerIdentity, ProviderAdapter
from qbittensor.miner.providers.registry import get_adapter
from qbittensor.utils.services.job import JobClient
from qbittensor.utils.services.telemetry import emit_from_registry
from qbittensor.miner.runtime.observability.error_reporter import build_error_event
from qbittensor.miner.runtime.flows.completion_flow import persist_completion as _persist_completion_external
from qbittensor.miner.runtime.repository import (
    insert_pending,
    list_open_executions,
    persist_failed,
    update_to_queued,
)
from qbittensor.miner.runtime.types import UploadDataResponse, _TrackedJob

from qbittensor.constants import (
    JOB_POLL_INTERVAL_S,
    LOCK_TIMEOUT_S,
    STATUS_UPDATE_INTERVAL_S,
)

TIMER_COUNTDOWN: timedelta = timedelta(seconds=30)


class JobRegistry:
    """
    Main thread: Bittensor operations (handled by Miner class)
    Provider thread: All provider calls (submit, poll, cancel, get_availability, get_pricing)
    Job server thread: All job endpoint communication
    """

    def __init__(
            self,
            db: DatabaseManager,
            keypair: "bt.Keypair",
            poll_interval_s: float = JOB_POLL_INTERVAL_S,
            adapter: Optional[ProviderAdapter] = None,
            job_client: JobClient | None = None) -> None:
        self.database_manager = db
        self.db = db
        self.keypair = keypair
        self.poll_interval_s = poll_interval_s
        self._jobs: Dict[str, _TrackedJob] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._submit_lock = threading.Lock()
        self._submit_threads: list[threading.Thread] = []

        self._default_device = None
        self.default_device_id: str | None = None

        self._TrackedJob = _TrackedJob
        self.LOCK_TIMEOUT_S = LOCK_TIMEOUT_S
        self.STATUS_UPDATE_INTERVAL_S = STATUS_UPDATE_INTERVAL_S

        self._provider_thread: Optional[threading.Thread] = None
        self._job_server_thread: Optional[threading.Thread] = None
        if job_client is None:
            raise ValueError("job_client must be provided to JobRegistry")
        self._job_client: JobClient | None = job_client
        self._on_job_completed: Optional[Callable[[str, Optional[float]], None]] = None

        self._status_queue: "queue.Queue[Dict]" = queue.Queue(maxsize=10)
        self._error_queue: "queue.Queue[Dict]" = queue.Queue(maxsize=100)

        self._last_status_update = time.time()
        self._availability_cache = None
        self._pricing_cache = None
        self._last_avail_check = 0.0
        self._last_price_check = 0.0
        self._availability_check_interval_s = 15.0
        self._pricing_check_interval_s = 60.0

        try:
            self._max_inflight: int = int(os.getenv("MINER_MAX_INFLIGHT", "1000"))
        except Exception:
            self._max_inflight = 1000

        self.adapter: ProviderAdapter = adapter if adapter is not None else get_adapter()
        devices = []
        try:
            devices = self.adapter.list_devices() if hasattr(self.adapter, "list_devices") else []
        except Exception as e:
            bt.logging.error(f" [provider] list_devices failed: {e}")
            try:
                event = build_error_event(
                    stage="provider.devices",
                    code="EXCEPTION",
                    message=str(e),
                    retryable=True,
                    execution_id=None,
                    provider_job_id=None,
                    device_id=None,
                    context=None,
                )
                self._enqueue_error_event(event)
            except Exception:
                pass
        self._default_device = devices[0] if len(devices) > 0 else None
        self.default_device_id: str | None = self._default_device.device_id if self._default_device else None

    def set_on_job_completed(self, callback: Callable[[str, Optional[float]], None]) -> None:
        """
        Register a callback invoked when a job completes.
        The callback receives (execution_id, cost_usd).
        """

        self._on_job_completed = callback
        bt.logging.debug("Registered on_job_completed callback")

    def _collect_status_data(self) -> None:
        """Collect status data from provider and enqueue for job server thread (inline)."""

        try:
            availability = None
            pricing = None
            try:
                availability = self.adapter.get_availability(self.default_device_id)
            except Exception as e:
                try:
                    event = build_error_event(
                        stage="provider.availability",
                        code="EXCEPTION",
                        message=str(e),
                        retryable=True,
                        execution_id=None,
                        provider_job_id=None,
                        device_id=self.default_device_id,
                        context=None,
                    )
                    self._enqueue_error_event(event)
                except Exception:
                    pass
            try:
                pricing = self.adapter.get_pricing(self.default_device_id)
            except Exception as e:
                try:
                    event = build_error_event(
                        stage="provider.pricing",
                        code="EXCEPTION",
                        message=str(e),
                        retryable=True,
                        execution_id=None,
                        provider_job_id=None,
                        device_id=self.default_device_id,
                        context=None,
                    )
                    self._enqueue_error_event(event)
                except Exception:
                    pass

            identity = MinerIdentity(
                device_id=self.default_device_id, provider=(
                    self._default_device.provider if self._default_device else getattr(
                        self.adapter, "__class__").__name__.replace(
                        "Adapter", "").lower()), vendor=(
                    self._default_device.vendor if self._default_device else None), device_type=(
                        self._default_device.device_type if self._default_device else (
                            "QPU" if (
                                self.default_device_id and "qpu" in self.default_device_id) else "SIMULATOR")))

            caps_list = self.adapter.list_capabilities()
            caps = None
            if len(caps_list) > 0:
                cap0 = caps_list[0]
                caps = Capabilities(num_qubits=cap0.num_qubits, basis_gates=cap0.basis_gates, extras=cap0.extras)

            status_data = {
                "identity": identity,
                "capabilities": caps,
                "availability": availability,
                "pricing": pricing,
            }

            try:
                self._status_queue.put_nowait(status_data)
            except queue.Full:
                try:
                    self._status_queue.get_nowait()
                    self._status_queue.put_nowait(status_data)
                except Exception:
                    pass
        except Exception as e:
            bt.logging.trace(f" Failed to collect status data: {e}")

    def _update_job_server_status(self) -> None:
        """Backward compatibility wrapper for tests - collects and sends status immediately."""
        self._collect_status_data()
        try:
            status_data = self._status_queue.get_nowait()
            self._send_status_to_job_server(status_data)
        except queue.Empty:
            pass

    def _send_status_to_job_server(self, status_data: Dict) -> None:
        from qbittensor.miner.runtime.io.job_server import send_status_to_job_server
        send_status_to_job_server(self, status_data)

    def start(self) -> None:
        """Start the provider and job server threads."""
        if self._provider_thread is None or not self._provider_thread.is_alive():
            from qbittensor.miner.runtime.threads.provider_thread import run_provider
            self._provider_thread = threading.Thread(
                target=run_provider, args=(
                    self,), name="Provider Thread", daemon=True)
            self._provider_thread.start()

        if self._job_server_thread is None or not self._job_server_thread.is_alive():
            from qbittensor.miner.runtime.threads.status_thread import run_job_server
            self._job_server_thread = threading.Thread(
                target=run_job_server, args=(
                    self,), name="Job Server Thread", daemon=True)
            self._job_server_thread.start()

    def request_stop(self) -> None:
        """Signal worker threads to leave their loops. Safe from a signal handler."""
        self._stop.set()

    def stop(self) -> None:
        """Stop all threads gracefully."""
        self.request_stop()
        if self._provider_thread is not None:
            self._provider_thread.join(timeout=2.0)
        if self._job_server_thread is not None:
            self._job_server_thread.join(timeout=2.0)

    def spawn_submit(self, target: Callable[[], None], name: str) -> threading.Thread:
        """Run a submit off the axon thread and keep it across SIGTERM until it persists."""
        thread = threading.Thread(target=target, name=name, daemon=False)
        with self._submit_lock:
            self._submit_threads = [item for item in self._submit_threads if item.is_alive()]
            self._submit_threads.append(thread)
        thread.start()
        return thread

    def join_submits(self, timeout: float) -> None:
        """Wait for in-flight submits so a provider job id is on disk before exit."""
        deadline = time.monotonic() + max(0.0, timeout)
        with self._submit_lock:
            threads = [item for item in self._submit_threads if item.is_alive()]
        for thread in threads:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(timeout=remaining)

    def restore_open_executions(self) -> int:
        """Reload non-terminal executions so a restart keeps polling them."""
        try:
            rows = list_open_executions(self)
        except Exception as exc:
            bt.logging.error(f"open execution query failed: {exc}")
            return 0
        restored = 0
        for execution_id, validator_hotkey, provider_job_id, device_id, shots, metadata_json in rows:
            meta: Dict = {}
            if metadata_json:
                try:
                    parsed = json.loads(metadata_json)
                    if isinstance(parsed, dict):
                        meta = parsed
                except Exception:
                    meta = {}
            if provider_job_id:
                target = device_id or meta.get("backend_class_id") or "restored"
                handle = JobHandle(provider_job_id=str(provider_job_id), device_id=str(target))
                tracked = _TrackedJob(
                    execution_id=str(execution_id),
                    validator_hotkey=str(validator_hotkey or ""),
                    handle=handle,
                )
                with self._lock:
                    self._jobs[str(execution_id)] = tracked
                restored += 1
                continue
            url = meta.get("input_data_url")
            if not url:
                bt.logging.warning(
                    f"execution {execution_id} is open with no provider job id and no circuit url"
                )
                try:
                    persist_failed(
                        self,
                        execution_id=str(execution_id),
                        validator_hotkey=str(validator_hotkey or ""),
                        provider=None,
                        provider_job_id=None,
                        device_id=str(device_id) if device_id else None,
                        error_message="Lost before provider submit",
                        metadata={"stage": "restore"},
                    )
                except Exception as exc:
                    bt.logging.error(
                        f"failed to mark unrestorable execution {execution_id}: {exc}"
                    )
                continue
            cfg = meta.get("configuration_data")
            if not isinstance(cfg, dict):
                cfg = None
            backend = meta.get("backend_class_id")
            if backend is not None:
                backend = str(backend)
            self.spawn_submit(
                lambda eid=str(execution_id), vhk=str(validator_hotkey or ""), u=str(url), s=shots, c=cfg, b=backend: self.submit(
                    execution_id=eid,
                    input_data_url=u,
                    validator_hotkey=vhk,
                    shots=s,
                    configuration_data=c,
                    backend_class_id=b,
                ),
                name=f"resume-{str(execution_id)[:8]}",
            )
            restored += 1
        if restored:
            bt.logging.info(f"Restored {restored} open execution(s)")
        return restored

    def submit(
        self,
        execution_id: str,
        input_data_url: str,
        validator_hotkey: str,
        shots: int | None = None,
        configuration_data: dict | None = None,
        backend_class_id: str | None = None,
    ) -> None:
        """Accept locally, then submit to provider and mark Queued/Running downstream."""
        class_id = str(backend_class_id).strip() if backend_class_id else ""
        if not class_id:
            bt.logging.error(
                f"Refusing execution {execution_id}: claim has no backend class"
            )
            try:
                from qbittensor.miner.runtime.repository import persist_failed
                persist_failed(
                    self,
                    execution_id=execution_id,
                    validator_hotkey=validator_hotkey,
                    provider=None,
                    provider_job_id=None,
                    device_id=None,
                    error_message="Claim has no backend class",
                    metadata={"stage": "submit"},
                )
            except Exception:
                pass
            return
        try:
            insert_pending(
                self,
                execution_id=execution_id,
                validator_hotkey=validator_hotkey,
                handle=type("H", (), {"provider_job_id": None, "device_id": None})(),
                shots=shots,
                input_data_url=input_data_url,
                configuration_data=configuration_data,
                backend_class_id=backend_class_id,
            )
        except Exception as e:
            bt.logging.debug(f" Failed to persist initial Pending state for {execution_id}: {e}")

        qasm = self._download_qasm(input_data_url)
        bt.logging.info(f" Successfully downloaded QASM for execution {execution_id}")
        if qasm is None:
            bt.logging.debug(f" Failed to download QASM for execution {execution_id}")
            emit_from_registry(self, "miner_record_submit_fail", execution_id, "qasm_download")
            try:
                from qbittensor.miner.runtime.repository import persist_failed
                persist_failed(
                    self,
                    execution_id=execution_id,
                    validator_hotkey=validator_hotkey,
                    provider=None,
                    provider_job_id=None,
                    device_id=class_id,
                    error_message="Failed to download QASM for prepare",
                    metadata={"stage": "prepare"},
                )
            except Exception:
                pass
            return

        try:
            handle = self.adapter.submit(
                circuit_data=qasm,
                device_id=class_id,
                shots=shots,
                configuration_data=configuration_data,
            )
        except Exception as e:
            bt.logging.error(f"Provider submit failed for execution {execution_id}: {e}")
            emit_from_registry(self, "miner_record_submit_fail", execution_id, str(e))
            try:
                event = build_error_event(
                    stage="provider.submit",
                    code="EXCEPTION",
                    message=str(e),
                    retryable=True,
                    execution_id=execution_id,
                    provider_job_id=None,
                    device_id=class_id,
                    context=None,
                )
                self._enqueue_error_event(event)
            except Exception:
                pass
            try:
                from qbittensor.miner.runtime.repository import persist_failed
                persist_failed(
                    self,
                    execution_id=execution_id,
                    validator_hotkey=validator_hotkey,
                    provider=None,
                    provider_job_id=None,
                    device_id=class_id,
                    error_message=str(e),
                    metadata={"stage": "submit"},
                )
            except Exception:
                pass
            return

        try:
            update_to_queued(self, execution_id=execution_id, handle=handle)
        except Exception as e:
            bt.logging.error(f"Failed to persist provider job id for {execution_id}: {e}")
        private_id = str(getattr(handle, "provider_job_id", "") or "")
        emit_from_registry(self, "miner_record_private_submit", execution_id, private_id)
        tracked = _TrackedJob(execution_id=execution_id, validator_hotkey=validator_hotkey, handle=handle)
        with self._lock:
            self._jobs[execution_id] = tracked
        self.start()

    def _download_qasm(self, url: str) -> str | None:
        """Download QASM data from a URL."""
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as req_e:
            bt.logging.debug(f"HTTP request failed for execution url: {url}: {req_e}")

    def cancel(self, execution_id: str) -> None:
        with self._lock:
            tracked = self._jobs.get(execution_id)
        if not tracked:
            return
        try:
            self.adapter.cancel(tracked.handle)
        except Exception as e:
            bt.logging.debug(f"Cancel failed for job {execution_id}: {e}")
            try:
                event = build_error_event(
                    stage="provider.cancel",
                    code="EXCEPTION",
                    message=str(e),
                    retryable=True,
                    execution_id=execution_id,
                    provider_job_id=getattr(tracked.handle, "provider_job_id", None),
                    device_id=getattr(tracked.handle, "device_id", None),
                    context=None,
                )
                self._enqueue_error_event(event)
            except Exception:
                pass

    def process_submissions_sync(self) -> None:
        """Legacy method for test compatibility - now a no-op since we submit directly."""
        pass

    def _send_error_to_job_server(self, error_data: Dict) -> None:
        from qbittensor.miner.runtime.io.job_server import send_error_to_job_server
        send_error_to_job_server(self, error_data)

    def _enqueue_error_event(self, event: Dict) -> None:
        """Enqueue a provider error event for the job server thread to deliver."""
        try:
            self._error_queue.put_nowait(event)
        except queue.Full:
            try:
                _ = self._error_queue.get_nowait()
                self._error_queue.put_nowait(event)
            except Exception:
                pass

    def get_cached_availability(self):
        """Get cached availability (for throttling decisions)."""
        return self._availability_cache

    def get_cached_pricing(self):
        """Get cached pricing (for throttling decisions)."""
        return self._pricing_cache

    def is_tracking(self, execution_id: str) -> bool:
        """Return True if a execution_id is currently being tracked (submitted but not finalized)."""
        with self._lock:
            return execution_id in self._jobs

    def _persist_completion(self, tracked: _TrackedJob) -> None:
        """Insert completed job into executions tables (delegated)."""
        _persist_completion_external(self, tracked)

    def _get_upload_data(self):
        """Get upload data from the jobs api."""
        if self._job_client is None:
            raise ValueError("job_client must be provided to JobRegistry")
        data = self._job_client.request_upload_slot()
        return UploadDataResponse(**data)

    def get_inflight_count(self) -> int:
        """Count non-terminal executions in the local DB (queued/running/pending)."""
        try:
            query = """
                SELECT COUNT(1) FROM executions
                WHERE status NOT IN ('Completed', 'Failed')
            """
            with self.database_manager.lock:
                rows = self.database_manager.query(query)
            if isinstance(rows, list) and rows:
                cnt = rows[0][0]
                try:
                    return int(cnt)
                except Exception:
                    return 0
        except Exception:
            return 0

    def get_pending_count(self) -> int:
        """Count locally accepted but not yet submitted jobs (Pending)."""
        try:
            query = """
                SELECT COUNT(1) FROM executions
                WHERE status = 'Pending'
            """
            with self.database_manager.lock:
                rows = self.database_manager.query(query)
            if isinstance(rows, list) and rows:
                cnt = rows[0][0]
                try:
                    return int(cnt)
                except Exception:
                    return 0
        except Exception:
            return 0
