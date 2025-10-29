from __future__ import annotations

import json
from typing import Any, Dict, Optional

from qbittensor.validator.utils.execution_status import ExecutionStatus
from qbittensor.utils.timestamping import timestamp_str


def insert_pending(registry, *, execution_id: str, validator_hotkey: str, handle, shots: Optional[int]) -> None:
    ts = timestamp_str()
    query = """
        INSERT OR REPLACE INTO executions (
            execution_id, upload_data_id, validator_hotkey, provider, provider_job_id, device_id, status,
            shots, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    values = (
        execution_id,
        None,
        validator_hotkey,
        getattr(getattr(registry, "_default_device", None), "provider", None) if hasattr(registry, "_default_device") else None,
        getattr(handle, "provider_job_id", None),
        getattr(handle, "device_id", None),
        "Pending",
        shots,
        ts,
    )
    with registry.database_manager.lock:
        registry.database_manager.query_and_commit_with_values(query, values)


def update_to_queued(registry, *, execution_id: str, handle) -> None:
    ts = timestamp_str()
    query = """
        UPDATE executions 
        SET status = ?, provider_job_id = ?, device_id = ?, timestamp = ?
        WHERE execution_id = ?
    """
    values = (
        "Queued",
        getattr(handle, "provider_job_id", None),
        getattr(handle, "device_id", None),
        ts,
        execution_id,
    )
    with registry.database_manager.lock:
        registry.database_manager.query_and_commit_with_values(query, values)


def persist_failed(
    registry,
    *,
    execution_id: str,
    validator_hotkey: str,
    provider: Optional[str],
    provider_job_id: Optional[str],
    device_id: Optional[str],
    error_message: Optional[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    ts = timestamp_str()
    query = """
        INSERT OR REPLACE INTO executions (
            execution_id, upload_data_id, validator_hotkey, provider, provider_job_id, device_id, status,
            shots, timestamp, metadata_json, completed_at, errorMessage
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    values = (
        execution_id,
        None,
        validator_hotkey,
        provider,
        provider_job_id,
        device_id,
        ExecutionStatus.FAILED,
        None,
        ts,
        json.dumps(metadata or {}),
        ts,
        error_message,
    )
    with registry.database_manager.lock:
        registry.database_manager.query_and_commit_with_values(query, values)


def persist_completed(registry, *, tracked, receipt, upload_data_id: str) -> None:
    ts = timestamp_str()
    query = """
        INSERT OR REPLACE INTO executions (
            execution_id, upload_data_id, validator_hotkey, provider, provider_job_id, device_id, status, cost, shots,
            timestamp, timestamps_json, metadata_json, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    values = (
        tracked.execution_id,
        upload_data_id,
        tracked.validator_hotkey,
        getattr(receipt, "provider", None),
        getattr(receipt, "provider_job_id", None),
        getattr(receipt, "device_id", None),
        ExecutionStatus.COMPLETED,
        getattr(receipt, "cost", None),
        getattr(receipt, "shots", None),
        ts,
        json.dumps(getattr(receipt, "timestamps", None) or {}),
        json.dumps(getattr(receipt, "metadata", None) or {}),
        ts,
    )
    with registry.database_manager.lock:
        registry.database_manager.query_and_commit_with_values(query, values)


def update_status(registry, *, execution_id: str, status: str) -> None:
    ts = timestamp_str()
    query = """
        UPDATE executions 
        SET status = ?, timestamp = ?
        WHERE execution_id = ?
    """
    with registry.database_manager.lock:
        registry.database_manager.query_and_commit_with_values(query, (status, ts, execution_id))


