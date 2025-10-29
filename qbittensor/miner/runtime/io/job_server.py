import bittensor as bt
from typing import Any, Dict, Optional
from qbittensor.miner.runtime.types import (
    Pricing as _PricingModel,
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
            
        elif isinstance(getattr(availability, "availability", None), str):
            is_available = availability.availability.upper() == "ONLINE"

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
            if getattr(availability, "is_available", None) is False and isinstance(getattr(availability, "status_msg", None), str) and "local_queue_full" in availability.status_msg:
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


def _send_backend_patch(registry, payload: Dict[str, Any]) -> None:
    try:
        accepting = payload.get("accepting_jobs")
        qdepth = payload.get("queue_depth")
        status = payload.get("status")
        try:
            hotkey = getattr(getattr(registry, "_request_manager", None), "_keypair", None)
            hotkey = getattr(hotkey, "ss58_address", None)
        except Exception:
            hotkey = None
        bt.logging.debug(f"[job_server] PATCH /backends sending (accepting_jobs={accepting}, queue_depth={qdepth}, status={status}, hotkey={hotkey})")
    except Exception:
        pass
    registry._request_manager.patch(endpoint="backends", json=payload)


def send_status_to_job_server(registry, status_data: dict) -> None:
    """Send availability/pricing to platform via PATCH /v{API_VERSION}/backends."""
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
        inflight_count = int(status_data.get("_inflight_count") or 0)
        provider_queue = getattr(availability, "pending_jobs", None) if availability is not None else None
        accepting_jobs, queue_depth = _build_availability_fields(availability, pending_count=pending_count, provider_queue=provider_queue)
        snake_price = _build_pricing_fields(pricing)
        metadata = _build_metadata(identity, availability, caps, registry)

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
        pricing_model = _PricingModel(
            per_task=snake_price.get("per_task"),
            per_shot=snake_price.get("per_shot"),
            per_minute=snake_price.get("per_minute"),
        )
        payload_model = _PatchBackendRequestModel(
            accepting_jobs=accepting_jobs,
            status=status_enum,
            queue_depth=queue_depth,
            metadata=metadata,
            pricing=pricing_model,
        )
        try:
            bt.logging.info(f"[job_server] Backend status ready (accepting_jobs={accepting_jobs}, queue_depth={queue_depth}, status={status_enum})")
        except Exception:
            pass
        _send_backend_patch(registry, payload_model.model_dump(mode='json'))
    except Exception as e:
        bt.logging.trace(f" Failed to send status to job server: {e}")


def send_error_to_job_server(registry, error_data: dict) -> None:
    """Report execution status via PATCH /v{API_VERSION}/executions/:execution_id."""
    try:
        execution_id = error_data.get("job_id") or error_data.get("execution_id")
        message = error_data.get("error") or error_data.get("message") or ""
        
        if execution_id:
            registry._request_manager.patch(endpoint=f"executions/{execution_id}", json={"status": "Failed", "message": message})
    except Exception as e:
        bt.logging.trace(f"[job_server_ops] Failed to send error to job server: {e}")


