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

"""Typed client for the Open Quantum job API."""

from typing import Optional, Dict, Any, List

import requests

from qbittensor.utils.request.request_manager import RequestManager
from qbittensor.utils.env import get_api_config
from qbittensor.utils.services.exceptions import (
    JobApiError,
    JobAuthError,
    _parse_platform_error_body,
)
from qbittensor.protocol import COLLECT_SYNAPSE_ID


class JobClient:

    def __init__(
        self,
        keypair: Any,
        base_url: Optional[str] = None,
        *,
        tensorauth_url: Optional[str] = None,
        api_version: Optional[str] = None,
        node_type: str = "miner",
        network: str = "",
        netuid: int | None = None,
    ):
        cfg = get_api_config()

        job_url = base_url or cfg.job_api_url
        if not job_url:
            raise ValueError("Job API URL is required (JOB_API_URL or JOB_SERVER_URL)")

        self.keypair = keypair
        self.ca_base_url = (cfg.ca_base_url or "").rstrip("/")
        self.request_manager = RequestManager(
            keypair,
            node_type=node_type,
            network=network,
            job_api_url=job_url,
            tensorauth_url=tensorauth_url,
            telemetry_api_url=None,
            api_version=api_version or cfg.api_version,
            netuid=netuid,
        )

    # ------------------------------------------------------------------
    # High-level typed methods (examples of current usage)
    # ------------------------------------------------------------------

    def get_execution_for_miner(self, miner_hotkey: str) -> Optional[Dict[str, Any]]:
        """Fetch next execution for a miner (or collect-only marker)."""
        endpoint = "executions"
        params = {"miner_hotkey": miner_hotkey}
        try:
            resp = self.request_manager.get(endpoint, params=params, ignore_codes=[404])
        except Exception as e:
            raise JobApiError(f"Failed to fetch execution: {e}") from e

        if resp.status_code == 404:
            return None
        if resp.status_code == 204:
            return {"execution_id": COLLECT_SYNAPSE_ID, "shots": 0}
        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception as e:
                raise JobApiError("Failed to parse execution response") from e
        if resp.status_code in (401, 403):
            parsed = _parse_platform_error_body(resp.text)
            raise JobAuthError("Unauthorized for job API", status_code=resp.status_code, **parsed)
        raise JobApiError(
            f"Unexpected status {resp.status_code}",
            status_code=resp.status_code,
            response_text=resp.text,
        )

    def get_execution_for_classes(
        self,
        classes: List[str],
        actor_id: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        """Next PUBLIC execution for these classes. HTTP 204 is collect-only."""
        endpoint = "executions"
        joined = ",".join(c.strip() for c in classes if c and str(c).strip())
        params: Dict[str, Any] = {"backend_classes": joined}
        if actor_id:
            params["actor_id"] = actor_id
        try:
            resp = self.request_manager.get(endpoint, params=params, ignore_codes=[404])
        except Exception as e:
            raise JobApiError(f"Failed to fetch execution for classes: {e}") from e

        if resp.status_code == 404:
            return None
        if resp.status_code == 204:
            return {"execution_id": COLLECT_SYNAPSE_ID, "shots": 0}
        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception as e:
                raise JobApiError("Failed to parse execution response") from e
        if resp.status_code in (401, 403):
            parsed = _parse_platform_error_body(resp.text)
            raise JobAuthError("Unauthorized for job API", status_code=resp.status_code, **parsed)
        raise JobApiError(
            f"Unexpected status {resp.status_code}",
            status_code=resp.status_code,
            response_text=resp.text,
        )

    def report_spark(self, classes: List[str]) -> None:
        """POST spark/report {classes} so platform freshness updates."""
        body = {"classes": [str(c).strip() for c in classes if c and str(c).strip()]}
        try:
            self.request_manager.post(
                "spark/report",
                json=body,
                ignore_codes=[404],
            )
        except Exception as e:
            raise JobApiError(f"Failed to report spark: {e}") from e

    def request_upload_slot(self) -> Dict[str, Any]:
        """Request a presigned upload URL for results."""
        endpoint = "executions/upload"
        try:
            result = self.request_manager.post(endpoint, json={})
            return result.json()
        except Exception as e:
            raise JobApiError(f"Failed to request upload slot: {e}") from e

    def patch_backend(self, payload: Dict[str, Any]) -> None:
        """Report miner backend/availability/pricing. 404/403 are no-ops for mapping-only miners."""
        try:
            self.request_manager.patch(
                endpoint="backends",
                json=payload,
                ignore_codes=[404, 403],
            )
        except Exception as e:
            raise JobApiError(f"Failed to patch backend: {e}") from e

    def patch_execution_status(self, execution_id: str, status: str, message: Optional[str] = None) -> None:
        """Update execution status on the platform."""
        body: Dict[str, Any] = {"status": status}
        if message:
            body["message"] = message
        try:
            resp = self.request_manager.patch(endpoint=f"executions/{execution_id}", json=body)
            self._raise_if_http_error(resp, f"patch execution status {execution_id}")
        except JobApiError:
            raise
        except Exception as e:
            raise JobApiError(f"Failed to patch execution status: {e}") from e

    def patch_execution_cost(self, execution_id: str, cost: float) -> None:
        """Report cost confirmation for an execution."""
        endpoint = f"executions/{execution_id}/cost"
        try:
            resp = self.request_manager.patch(endpoint, json={"cost": cost})
            self._raise_if_http_error(resp, f"patch execution cost {execution_id}")
        except JobApiError:
            raise
        except Exception as e:
            raise JobApiError(f"Failed to patch execution cost: {e}") from e

    def get_weight_epoch(self) -> Dict[str, Any]:
        """Frozen cost book + prices for this weight epoch. 403 if inactive."""
        try:
            resp = self.request_manager.get("executions/weights/epoch")
            if resp.status_code != 200:
                raise JobApiError(
                    f"Unexpected status {resp.status_code} from weight epoch",
                    status_code=resp.status_code,
                    response_text=resp.text,
                )
            data = resp.json()
            if not isinstance(data, dict):
                raise JobApiError("Weight epoch response is not an object")
            return data
        except JobApiError:
            raise
        except Exception as e:
            raise JobApiError(f"Failed to fetch weight epoch: {e}") from e

    @staticmethod
    def _raise_if_http_error(resp: Any, what: str) -> None:
        status = getattr(resp, "status_code", None)
        if status is None:
            return
        if 200 <= int(status) <= 299:
            return
        text = getattr(resp, "text", None)
        parsed = _parse_platform_error_body(text if isinstance(text, str) else None)
        detail = parsed.get("message")
        if isinstance(detail, list):
            detail = "; ".join(str(x) for x in detail)
        msg = f"{what} failed"
        if isinstance(detail, str) and detail.strip():
            msg = f"{msg}: {detail.strip()}"
        raise JobApiError(
            msg,
            status_code=int(status),
            response_text=text if isinstance(text, str) else None,
            error_code=parsed.get("error_code"),
        )

    def fetch_certificate_pem(self, serial_hex: str) -> Optional[str]:
        if not self.ca_base_url or not serial_hex:
            return None
        try:
            resp = requests.get(
                f"{self.ca_base_url}/v1/certificates/{serial_hex.lower()}",
                timeout=7,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            pem = data.get("certificate_pem") if isinstance(data, dict) else None
            return pem if isinstance(pem, str) and pem else None
        except Exception:
            return None

    def verify_ca_proof(
        self,
        payload: str,
        signature_b64: str,
        certificate_pem: str,
    ) -> bool:
        if not self.ca_base_url:
            return False
        try:
            resp = requests.post(
                f"{self.ca_base_url}/v1/verify",
                json={
                    "payload": payload,
                    "signature_b64": signature_b64,
                    "certificate_pem": certificate_pem,
                },
                timeout=7,
            )
            if not (200 <= resp.status_code < 300):
                return False
            data = resp.json()
            return bool(isinstance(data, dict) and data.get("valid"))
        except Exception:
            return False

    def patch_execution(self, execution_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """General method to patch an execution (for status, cost, etc.)."""
        try:
            resp = self.request_manager.patch(f"executions/{execution_id}", json=body)
            self._raise_if_http_error(resp, f"patch execution {execution_id}")
            try:
                data = resp.json()
            except Exception:
                return {}
            return data if isinstance(data, dict) else {}
        except JobApiError:
            raise
        except Exception as e:
            raise JobApiError(f"Failed to patch execution {execution_id}: {e}") from e

    def get_executions(self, miner_hotkey: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """General fetch for executions, optionally filtered."""
        endpoint = "executions"
        params = {"miner_hotkey": miner_hotkey} if miner_hotkey else {}
        try:
            resp = self.request_manager.get(endpoint, params=params, ignore_codes=[404])
            if resp.status_code in (404, 204):
                return None
            return resp.json()
        except Exception as e:
            raise JobApiError(f"Failed to get executions: {e}") from e
