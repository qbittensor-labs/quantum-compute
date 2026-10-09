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

import bittensor as bt
from typing import Any, Dict, Optional
from qbittensor.miner.runtime.types import (
    PatchBackendRequest as _PatchBackendRequestModel,
    MinerStatus as _MinerStatus,
)


def _build_availability_fields(availability, *, pending_count: int, provider_queue: Optional[int]) -> tuple[bool, int]:

    accepting_jobs = True
    queue_depth: int = 0

    if availability is not None:
        if getattr(availability, "pending_jobs", None) is not None:
            try:
                queue_depth += int(getattr(availability, "pending_jobs", 0) or 0)
            except Exception:
                pass

        next_available = getattr(availability, "next_available", None)
        if next_available is not None:
            next_available = str(next_available)

    try:
        queue_depth += int(pending_count or 0)
    except Exception:
        pass
    return accepting_jobs, queue_depth


def _build_pricing_fields(pricing: Dict[str, Any] | None) -> Dict[str, Any]:
    snake_price = {"per_task": None, "per_shot": None, "per_minute": None}
    p = pricing or {}
    if isinstance(p, dict):
        snake_price["per_task"] = p.get("perTask", p.get("per_task", snake_price["per_task"]))
        snake_price["per_shot"] = p.get("perShot", p.get("per_shot", snake_price["per_shot"]))
        snake_price["per_minute"] = p.get("perMinute", p.get("per_minute", snake_price["per_minute"]))
    return snake_price


def _build_metadata(identity, availability, caps, registry) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    try:
        if identity is not None:
            metadata["device_id"] = getattr(identity, "device_id", None)
            metadata["provider"] = getattr(identity, "provider", None)
            metadata["vendor"] = getattr(identity, "vendor", None)
            metadata["device_type"] = getattr(identity, "device_type", None)
    except Exception as e:
        try:
            bt.logging.error(f"[job_server_ops] Failed to enrich metadata: {e}")
        except Exception:
            pass
    try:
        if availability is not None:
            metadata["pending"] = getattr(availability, "pending_jobs", None)
            metadata["availability"] = getattr(availability, "availability", None)
            metadata["status_msg"] = getattr(availability, "status_msg", None)
            if getattr(
                availability,
                "is_available",
                None) is False and isinstance(
                getattr(
                    availability,
                    "status_msg",
                    None),
                    str) and "local_queue_full" in availability.status_msg:
                try:
                    metadata["local_inflight"] = registry.get_inflight_count()
                    metadata["max_inflight"] = getattr(registry, "_max_inflight", None)
                except Exception:
                    pass
    except Exception as e:
        bt.logging.trace(f"[job_server_ops] Failed to add availability to metadata: {e}")
    try:
        if caps is not None:
            metadata["num_qubits"] = getattr(caps, "num_qubits", None)
    except Exception as e:
        bt.logging.trace(f"[job_server_ops] Failed to add capabilities to metadata: {e}")
    return metadata


def send_status_to_job_server(registry, status_data: dict) -> None:
    """Keep local availability cache. Miners do not PATCH /backends."""
    try:
        try:
            bt.logging.debug("[job_server] Preparing backend status payload from collected provider data")
        except Exception:
            pass
        availability = status_data.get("availability")
        pricing = status_data.get("pricing") or {}
        identity = status_data.get("identity")
        caps = status_data.get("capabilities")

        pending_count = int(status_data.get("_pending_count") or 0)
        provider_queue = getattr(availability, "pending_jobs", None) if availability is not None else None
        accepting_jobs, queue_depth = _build_availability_fields(
            availability, pending_count=pending_count, provider_queue=provider_queue)
        metadata = _build_metadata(identity, availability, caps, registry)
        # Attach normalized pricing when present (fields are optional on the backend).
        snake_price = _build_pricing_fields(pricing)
        if any(v is not None for v in snake_price.values()):
            metadata["pricing"] = snake_price

        status_enum = _MinerStatus.ONLINE
        try:
            base_avail = getattr(availability, "availability", None)
            if isinstance(base_avail, str):
                up = base_avail.upper()
                if up == "OFFLINE":
                    status_enum = _MinerStatus.OFFLINE
                elif up == "MAINTENANCE":
                    status_enum = _MinerStatus.MAINTENANCE
                else:
                    status_enum = _MinerStatus.ONLINE
        except Exception:
            status_enum = _MinerStatus.ONLINE

        accepting_jobs = (pending_count < getattr(registry, "_max_inflight", 1000))
        if availability is not None and getattr(availability, "is_available", None) is False:
            accepting_jobs = False
        override = getattr(getattr(registry, "adapter", None), "get_accepting_jobs_override", None)
        if callable(override):
            try:
                forced = override()
            except Exception:
                forced = None
            if forced is False:
                accepting_jobs = False
            elif forced is True and availability is not None:
                accepting_jobs = True and (pending_count < getattr(registry, "_max_inflight", 1000))
        payload_model = _PatchBackendRequestModel(
            accepting_jobs=accepting_jobs,
            status=status_enum,
            queue_depth=queue_depth,
            metadata=metadata,
        )
        try:
            bt.logging.debug(
                f"[job_server] Local status (accepting_jobs={accepting_jobs}, queue_depth={queue_depth}, status={status_enum}); not PATCHing jobs"
            )
        except Exception:
            pass
        try:
            registry._availability_cache = availability
        except Exception:
            pass
    except Exception as e:
        bt.logging.trace(f" Failed to apply local status: {e}")


def send_error_to_job_server(registry, error_data: dict) -> None:
    """Errors stay local. Miners do not PATCH /executions/:id (validator reports via synapse)."""
    return
