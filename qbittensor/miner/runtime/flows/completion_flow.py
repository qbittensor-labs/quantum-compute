from __future__ import annotations

import json
import requests
import bittensor as bt
from typing import Any, Dict, Optional

from qbittensor.utils.timestamping import timestamp_str
from qbittensor.miner.runtime.repository import persist_failed as _db_persist_failed, persist_completed as _db_persist_completed
from qbittensor.miner.runtime.observability.error_reporter import build_error_event


def _valid_counts(counts: Dict[str, Any]) -> bool:
    if not isinstance(counts, dict) or not counts:
        return False
    for k, v in counts.items():
        if not isinstance(k, str) or any(c not in ("0", "1") for c in k):
            return False
        if not isinstance(v, int) or v < 0:
            return False
    return True


def _attempt_put(upload_url: str, payload: str) -> requests.Response:
    headers = {"Content-Type": "application/json"}
    response = requests.put(upload_url, data=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response


def _persist_failed_record(registry, tracked, receipt, error_message: str, meta: Optional[Dict[str, Any]] = None) -> None:
    provider_val = None
    device_val = getattr(tracked.handle, "device_id", None)
    provider_exec_id = getattr(tracked.handle, "provider_job_id", None)
    try:
        if receipt is not None:
            provider_val = getattr(receipt, "provider", None)
            if getattr(receipt, "device_id", None):
                device_val = getattr(receipt, "device_id", None)
            if getattr(receipt, "provider_job_id", None):
                provider_exec_id = getattr(receipt, "provider_job_id", None)
    except Exception:
        pass
    _db_persist_failed(
        registry,
        execution_id=tracked.execution_id,
        validator_hotkey=tracked.validator_hotkey,
        provider=provider_val,
        provider_job_id=provider_exec_id,
        device_id=device_val,
        error_message=error_message,
        metadata=meta or {},
    )


def _enqueue_error(registry, event: Dict[str, Any]) -> None:
    try:
        registry._enqueue_error_event(event)
    except Exception:
        pass


def _fail(registry, tracked, receipt, *, stage: str, code: str, message: str, retryable: bool, meta: Optional[Dict[str, Any]] = None, ctx: Optional[Dict[str, Any]] = None) -> bool:
    event = build_error_event(
        stage=stage,
        code=code,
        message=message,
        retryable=retryable,
        execution_id=tracked.execution_id,
        provider_job_id=getattr(tracked.handle, "provider_job_id", None),
        device_id=getattr(tracked.handle, "device_id", None),
        context=ctx,
    )
    _enqueue_error(registry, event)
    _persist_failed_record(registry, tracked, receipt, error_message=code if not message else message, meta=meta)
    return False


def persist_completion(registry, tracked) -> bool:
    """Insert completed job into executions tables.

    Returns True only when results were uploaded and DB persisted; otherwise False.
    """
    timestamp = timestamp_str()

    bt.logging.info(f" Starting completion persist for execution_id={tracked.execution_id}")

    # receipt
    try:
        receipt = registry.adapter.get_job_receipt(tracked.handle)
    except Exception as e:
        bt.logging.error(f" Provider receipt failed for execution {tracked.execution_id}: {e}")
        return _fail(
            registry,
            tracked,
            None,
            stage="provider.receipt",
            code="EXCEPTION",
            message=str(e),
            retryable=True,
            meta={"stage": "receipt"},
            ctx=None,
        )

    try:
        bt.logging.debug(
            f" Receipt fetched for execution_id={tracked.execution_id}: "
            f"provider={getattr(receipt, 'provider', None)}, "
            f"status={getattr(receipt, 'status', None)}, "
            f"device_id={getattr(receipt, 'device_id', None)}"
        )
    except Exception:
        pass

    try:
        upload_data = registry._get_upload_data()
    except Exception as e:
        bt.logging.error(f" Exception while requesting upload URL for execution {tracked.execution_id}: {e}")
        upload_data = None

    if not upload_data:
        bt.logging.error(f" Failed to get upload data for execution {tracked.execution_id}. Cannot upload results.")
        return _fail(
            registry,
            tracked,
            receipt,
            stage="upload.url_fetch",
            code="UNAVAILABLE",
            message="upload_data missing",
            retryable=True,
            meta={"stage": "upload_url"},
            ctx=None,
        )

    results = getattr(receipt, "results", None) or {}
    measurement_counts = results.get("measurementCounts", {}) if isinstance(results, dict) else {}
    try:
        bt.logging.debug(
            f" Extracted measurementCounts for execution_id={tracked.execution_id}: "
            f"num_bitstrings={(len(measurement_counts) if isinstance(measurement_counts, dict) else 0)}, "
            f"total_shots={(sum(measurement_counts.values()) if isinstance(measurement_counts, dict) and len(measurement_counts)>0 else 0)}"
        )
    except Exception:
        pass

    if not _valid_counts(measurement_counts):
        bt.logging.error(f" Invalid or missing measurement counts for execution {tracked.execution_id}. Failing job.")
        return _fail(
            registry,
            tracked,
            receipt,
            stage="results.counts_invalid",
            code="INVALID",
            message="measurementCounts invalid or missing",
            retryable=False,
            meta={"stage": "counts"},
            ctx=None,
        )

    try:
        counts_json = json.dumps(measurement_counts)
        bt.logging.info(f" Uploading results for execution {tracked.execution_id} to S3 (result_id={upload_data.id})")
        try:
            bt.logging.debug(
                f" Upload preflight: url_len={(len(upload_data.upload_url) if hasattr(upload_data, 'upload_url') and upload_data.upload_url else 0)}, "
                f"payload_bytes={len(counts_json)}"
            )
        except Exception:
            pass
        try:
            _attempt_put(upload_data.upload_url, counts_json)
        except requests.exceptions.RequestException as e:
            status_code = getattr(getattr(e, 'response', None), 'status_code', None)
            text = getattr(getattr(e, 'response', None), 'text', None)
            if status_code == 403:
                bt.logging.info(f" PUT returned 403; attempting single URL refresh for execution {tracked.execution_id}")
                try:
                    refreshed = registry._get_upload_data()
                    if not refreshed:
                        return _fail(
                            registry,
                            tracked,
                            receipt,
                            stage="upload.put",
                            code="HTTP_403_REFRESH_ERROR",
                            message="presigned URL refresh returned no data",
                            retryable=True,
                            meta={"stage": "upload_put", "http_status": 403},
                            ctx={"http_status": 403},
                        )
                    _attempt_put(refreshed.upload_url, counts_json)
                    upload_data = refreshed
                except Exception as e2:
                    bt.logging.error(f" PUT retry after refresh failed for execution {tracked.execution_id}: {e2}")
                    return _fail(
                        registry,
                        tracked,
                        receipt,
                        stage="upload.put",
                        code="HTTP_403_AFTER_REFRESH",
                        message=str(e2),
                        retryable=True,
                        meta={"stage": "upload_put", "http_status": 403},
                        ctx={"http_status": 403},
                    )
            else:
                try:
                    bt.logging.error(
                        f" Failed to upload results to S3 for execution {tracked.execution_id}: {e}; "
                        f"status_code={status_code}, response_body={(text[:200] if isinstance(text, str) else text)}"
                    )
                except Exception:
                    bt.logging.error(f" Failed to upload results to S3 for execution {tracked.execution_id}: {e}")
                return _fail(
                    registry,
                    tracked,
                    receipt,
                    stage="upload.put",
                    code=f"HTTP_{status_code or 'ERR'}",
                    message=str(e),
                    retryable=True,
                    meta={"stage": "upload_put", "http_status": status_code},
                    ctx={"http_status": status_code, "response_body": text},
                )
        bt.logging.info(f" Successfully uploaded results for execution {tracked.execution_id}")
    except Exception as e:
        bt.logging.error(f" Unexpected error uploading results for execution {tracked.execution_id}: {e}")
        return _fail(
            registry,
            tracked,
            receipt,
            stage="upload.put",
            code="EXCEPTION",
            message=str(e),
            retryable=True,
            meta={"stage": "upload_put"},
            ctx=None,
        )

    try:
        _db_persist_completed(registry, tracked=tracked, receipt=receipt, upload_data_id=upload_data.id)
    except Exception as e:
        bt.logging.error(f" DB persist of completion failed for execution {tracked.execution_id}: {e}")
        return _fail(
            registry,
            tracked,
            receipt,
            stage="db.persist_completed",
            code="EXCEPTION",
            message=str(e),
            retryable=True,
            meta=None,
            ctx=None,
        )

    return True


