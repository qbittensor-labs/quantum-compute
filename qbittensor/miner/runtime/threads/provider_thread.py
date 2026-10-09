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

from __future__ import annotations

import time
import bittensor as bt

from qbittensor.miner.runtime.observability.error_reporter import build_error_event
from qbittensor.miner.runtime.repository import persist_failed, update_status
from qbittensor.validator.utils.execution_status import ExecutionStatus


def run_provider(registry) -> None:
    bt.logging.info("| Provider Thread | Provider thread started")

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

        if registry._stop.wait(registry.poll_interval_s):
            break

    bt.logging.info("| Provider Thread | Provider thread stopped")


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
        new_status = status.status
        tracked.last_status = new_status

        # Only report telemetry on actual status changes (avoid spam like COMPLETED -> COMPLETED)
        if old_status != new_status:
            try:
                tsvc = getattr(registry, "_telemetry_service", None)
                if tsvc is not None:
                    try:
                        tsvc.miner_record_execution_status_change(
                            execution_id=execution_id,
                            new_status=new_status,
                            old_status=old_status,
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
                provider_name = getattr(
                    getattr(
                        registry,
                        "_default_device",
                        None),
                    "provider",
                    None) if hasattr(
                    registry,
                    "_default_device") else None
                platform_message = (status.message or "").strip() or None
                if status.status == "CANCELLED" and not platform_message:
                    platform_message = "Cancelled by request"
                persist_failed(
                    registry,
                    execution_id=tracked.execution_id,
                    validator_hotkey=tracked.validator_hotkey,
                    provider=provider_name,
                    provider_job_id=getattr(tracked.handle, "provider_job_id", None),
                    device_id=getattr(tracked.handle, "device_id", None),
                    error_message=platform_message,
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
        elif status.status == "UNKNOWN":
            try:
                provider_name = getattr(
                    getattr(
                        registry,
                        "_default_device",
                        None),
                    "provider",
                    None) if hasattr(
                    registry,
                    "_default_device") else None
                persist_failed(
                    registry,
                    execution_id=tracked.execution_id,
                    validator_hotkey=tracked.validator_hotkey,
                    provider=provider_name,
                    provider_job_id=getattr(tracked.handle, "provider_job_id", None),
                    device_id=getattr(tracked.handle, "device_id", None),
                    error_message="Provider lost track of job",
                    metadata={"provider_status": status.status},
                )
            except Exception as e:
                bt.logging.debug(f" Failed to persist UNKNOWN state for {execution_id}: {e}")
            finally:
                with registry._lock:
                    registry._jobs.pop(execution_id, None)
