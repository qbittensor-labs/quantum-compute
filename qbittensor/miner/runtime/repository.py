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

import json
from typing import Any, Dict, Optional

from qbittensor.validator.utils.execution_status import ExecutionStatus
from qbittensor.utils.time import timestamp_str


def insert_pending(
    registry,
    *,
    execution_id: str,
    validator_hotkey: str,
    handle,
    shots: Optional[int],
    input_data_url: Optional[str] = None,
    configuration_data: Optional[Dict[str, Any]] = None,
    backend_class_id: Optional[str] = None,
) -> None:
    ts = timestamp_str()
    resume: Dict[str, Any] = {}
    if input_data_url:
        resume["input_data_url"] = input_data_url
    if isinstance(configuration_data, dict) and configuration_data:
        resume["configuration_data"] = configuration_data
    if backend_class_id:
        resume["backend_class_id"] = backend_class_id
    query = """
        INSERT OR REPLACE INTO executions (
            execution_id, upload_data_id, validator_hotkey, provider, provider_job_id, device_id, status,
            shots, timestamp, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    values = (
        execution_id, None, validator_hotkey, getattr(
            getattr(
                registry, "_default_device", None), "provider", None) if hasattr(
            registry, "_default_device") else None, getattr(
                    handle, "provider_job_id", None), getattr(
                        handle, "device_id", None), "Pending", shots, ts,
        json.dumps(resume) if resume else None,
    )
    with registry.database_manager.lock:
        registry.database_manager.query_and_commit_with_values(query, values)


def list_open_executions(registry) -> list[tuple]:
    """Non-terminal rows. Used to resume polling after a restart."""
    query = """
        SELECT execution_id, validator_hotkey, provider_job_id, device_id, shots, metadata_json
        FROM executions
        WHERE status IN ('Pending', 'Queued', 'Running')
    """
    with registry.database_manager.lock:
        return list(registry.database_manager.query(query) or [])


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
