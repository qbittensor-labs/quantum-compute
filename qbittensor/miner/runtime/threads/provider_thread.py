from __future__ import annotations

import time
import bittensor as bt

from qbittensor.miner.runtime.observability.error_reporter import build_error_event
from qbittensor.miner.runtime.repository import persist_failed, update_status
from qbittensor.validator.utils.execution_status import ExecutionStatus


def run_provider(registry) -> None:
    bt.logging.info(f"| Provider Thread | Provider thread started")

    while not registry._stop.is_set():
        try:
            now = time.time()
            if now - registry._last_avail_check >= registry._availability_check_interval_s:
                try:
                    registry._availability_cache = registry.adapter.get_availability(registry.default_device_id)
                except Exception as e:
                    registry._availability_cache = None
                    try:
                        event = build_error_event(
                            stage="provider.availability",
                            code="EXCEPTION",
                            message=str(e),
                            retryable=True,
                            execution_id=None,
                            provider_job_id=None,
                            device_id=registry.default_device_id,
                            context=None,
                        )
                        registry._enqueue_error_event(event)
                    except Exception:
                        pass
                registry._last_avail_check = now

            if now - registry._last_price_check >= registry._pricing_check_interval_s:
                try:
                    registry._pricing_cache = registry.adapter.get_pricing(registry.default_device_id)
                except Exception as e:
                    registry._pricing_cache = None
                    try:
                        event = build_error_event(
                            stage="provider.pricing",
                            code="EXCEPTION",
                            message=str(e),
                            retryable=True,
                            execution_id=None,
                            provider_job_id=None,
                            device_id=registry.default_device_id,
                            context=None,
                        )
                        registry._enqueue_error_event(event)
                    except Exception:
                        pass
                registry._last_price_check = now

            poll_once(registry)

            if time.time() - registry._last_status_update >= registry.STATUS_UPDATE_INTERVAL_S:
                from qbittensor.miner.runtime.threads.status_thread import collect_status_data
                collect_status_data(registry)
                registry._last_status_update = time.time()

        except Exception as e:
            bt.logging.debug(f"Provider thread error: {e}")

        time.sleep(registry.poll_interval_s)

    bt.logging.info(f"| Provider Thread | Provider thread stopped")


def poll_once(registry) -> None:
    with registry._lock:
        items = list(registry._jobs.items())
    for execution_id, tracked in items:
        try:
            status = registry.adapter.poll(tracked.handle)
        except Exception as e:
            bt.logging.error(f" Provider poll failed for execution {execution_id}: {e}")
            try:
                event = build_error_event(
                    stage="provider.poll",
                    code="EXCEPTION",
                    message=str(e),
                    retryable=True,
                    execution_id=execution_id,
                    provider_job_id=getattr(tracked.handle, "provider_job_id", None),
                    device_id=getattr(tracked.handle, "device_id", None),
                    context=None,
                )
                registry._enqueue_error_event(event)
            except Exception:
                pass
            continue
        old_status = tracked.last_status
        tracked.last_status = status.status

        try:
            tsvc = getattr(registry, "_telemetry_service", None)
            if tsvc is not None:
                miner_uid = getattr(registry, "_miner_uid", None)
                miner_hotkey = None
                try:
                    miner_hotkey = getattr(getattr(registry, "keypair", None), "ss58_address", None)
                except Exception:
                    miner_hotkey = None
                if miner_hotkey is None:
                    try:
                        kp = getattr(getattr(registry, "_request_manager", None), "_keypair", None)
                        miner_hotkey = getattr(kp, "ss58_address", None)
                    except Exception:
                        miner_hotkey = None
                try:
                    tsvc.miner_record_execution_status_change(
                        execution_id=execution_id,
                        new_status=status.status,
                        old_status=old_status,
                        miner_uid=miner_uid,
                        miner_hotkey=miner_hotkey,
                    )
                except Exception:
                    pass
        except Exception:
            pass

        if status.status == "COMPLETED":
            from qbittensor.miner.runtime.flows.completion_flow import persist_completion
            finalized = persist_completion(registry, tracked)
            if finalized:
                with registry._lock:
                    registry._jobs.pop(execution_id, None)
        elif status.status in ("FAILED", "CANCELLED"):
            try:
                provider_name = getattr(getattr(registry, "_default_device", None), "provider", None) if hasattr(registry, "_default_device") else None
                persist_failed(
                    registry,
                    execution_id=tracked.execution_id,
                    validator_hotkey=tracked.validator_hotkey,
                    provider=provider_name,
                    provider_job_id=getattr(tracked.handle, "provider_job_id", None),
                    device_id=getattr(tracked.handle, "device_id", None),
                    error_message=("Cancelled by request" if status.status == "CANCELLED" else None),
                    metadata={"provider_status": status.status},
                )
            except Exception as e:
                bt.logging.debug(f" Failed to persist Failed/Cancelled state for {execution_id}: {e}")
            finally:
                with registry._lock:
                    registry._jobs.pop(execution_id, None)
        elif status.status in ("QUEUED", "RUNNING"):
            try:
                db_state = "Queued" if status.status == "QUEUED" else ExecutionStatus.RUNNING
                update_status(registry, execution_id=execution_id, status=db_state)
            except Exception as e:
                bt.logging.trace(f" Failed to update status for {execution_id}: {e}")


