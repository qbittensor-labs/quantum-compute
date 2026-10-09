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

from typing import Any, Dict, Optional


def _redact_context(context: Optional[Dict]) -> Optional[Dict]:
    if not isinstance(context, dict):
        return None
    try:
        redacted: Dict[str, Any] = {}
        for k, v in context.items():
            if k in ("upload_url", "presigned_url"):
                try:
                    redacted[k] = {"url_length": (len(v) if isinstance(v, str) else None)}
                except Exception:
                    redacted[k] = {"url_length": None}
            elif k in ("response_body", "body", "payload"):
                try:
                    s = str(v)
                    redacted[k] = s[:200]
                except Exception:
                    redacted[k] = None
            elif k in ("headers", "authorization", "auth"):
                redacted[k] = "<redacted>"
            else:
                redacted[k] = v
        return redacted
    except Exception:
        return None


def build_error_event(
    *,
    stage: str,
    code: str,
    message: str,
    retryable: bool,
    execution_id: Optional[str] = None,
    provider_job_id: Optional[str] = None,
    provider_execution_id: Optional[str] = None,
    device_id: Optional[str] = None,
    context: Optional[Dict] = None,
) -> Dict[str, Any]:
    event: Dict[str, Any] = {
        "stage": stage,
        "code": code,
        "message": message,
        "retryable": bool(retryable),
    }
    if execution_id is not None:
        event["execution_id"] = execution_id
    job_id_val = provider_job_id if provider_job_id is not None else provider_execution_id
    if job_id_val is not None:
        event["provider_job_id"] = job_id_val
    if device_id is not None:
        event["device_id"] = device_id
    redacted_ctx = _redact_context(context)
    if redacted_ctx is not None:
        event["context"] = redacted_ctx
    return event
