# The MIT License (MIT)
# Copyright © 2026 qBitTensor Labs

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urljoin

import bittensor as bt
import requests
from requests import Session

from qbittensor.miner.providers.base import JobReceipt
from qbittensor.utils.request.utils import make_session

from .config import OpenQuantumConfig, PRIVATE_PLAN_ID


def _map_status(provider_status: str) -> str:
    status = (provider_status or "").lower()
    if status in ("queued", "pending", "created", "submitted", "preparing"):
        return "QUEUED"
    if status in ("running", "executing", "in_progress"):
        return "RUNNING"
    if status in ("completed", "succeeded", "success", "done"):
        return "COMPLETED"
    if status in ("failed", "error"):
        return "FAILED"
    if status in ("canceled", "cancelled", "aborted"):
        return "CANCELLED"
    return "UNKNOWN"


class DryRunSimulator:
    def __init__(self) -> None:
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._next_id = 1

    def submit(self, circuit_data: str, device_id: str, shots: int | None) -> str:
        job_id = f"oq-sim-{self._next_id}"
        self._next_id += 1
        now = time.time()
        duration_s = max(1.0, min(8.0, len(circuit_data) / 800.0))
        self.jobs[job_id] = {
            "device_id": device_id,
            "submitted_at": now,
            "duration_s": duration_s,
            "status": "queued",
            "shots": shots,
        }
        return job_id

    def poll(self, job_id: str) -> Tuple[str, int]:
        job = self.jobs.get(job_id)
        if not job:
            return "UNKNOWN", 0
        if job["status"] in ("completed", "failed", "canceled"):
            return _map_status(job["status"]), 0
        elapsed = time.time() - job["submitted_at"]
        if elapsed < 0.2:
            job["status"] = "queued"
        elif elapsed < job["duration_s"]:
            job["status"] = "running"
        else:
            job["status"] = "completed"
        remaining = max(0, int(job["duration_s"] - max(0, elapsed)))
        return _map_status(job["status"]), remaining

    def cancel(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if job and job["status"] not in ("completed", "failed", "canceled"):
            job["status"] = "canceled"


class JobService:
    def __init__(self, config: OpenQuantumConfig) -> None:
        self._cfg = config
        self._sim = DryRunSimulator()
        self._session: Session = make_session(allowed_methods=["GET", "POST", "PUT"])
        self._last_quote: Optional[list] = None

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        token = self._cfg.bearer_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _url(self, path: str) -> str:
        base = self._cfg.scheduler_url.rstrip("/") + "/"
        return urljoin(base, path.lstrip("/"))

    def submit(
        self,
        circuit_data: str,
        device_id: str,
        shots: Optional[int],
        dry_run: bool,
        configuration_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        if dry_run:
            job_id = self._sim.submit(circuit_data, device_id, shots)
            bt.logging.info(f"[openquantum] (sim) submit device={device_id} -> {job_id}")
            return job_id
        return self._submit_private_job(
            circuit_data, device_id, configuration_data
        )

    def poll(
        self, job_id: str, dry_run: bool
    ) -> Tuple[str, int, Optional[str]]:
        if dry_run:
            status, remaining = self._sim.poll(job_id)
            return status, remaining, None
        body = self._get_job(job_id)
        if body is None:
            return "UNKNOWN", 0, None
        mapped = _map_status(str(body.get("status") or ""))
        raw_message = body.get("message")
        message = raw_message.strip() if isinstance(raw_message, str) else None
        return mapped, 0, message or None

    def cancel(self, job_id: str, dry_run: bool) -> None:
        if dry_run:
            self._sim.cancel(job_id)
            return
        url = self._url(f"v1/jobs/{job_id}")
        try:
            self._session.delete(url, headers=self._headers(), timeout=self._cfg.http_timeout_s)
        except Exception as e:
            bt.logging.debug(f"[openquantum] cancel failed job_id={job_id}: {e}")

    def receipt(self, job_id: str, device_id: str, dry_run: bool, shots: Optional[int]) -> JobReceipt:
        if dry_run:
            job = self._sim.jobs.get(job_id) or {}
            status = _map_status(str(job.get("status") or "UNKNOWN"))
            counts = {"00": 500, "11": 500} if status == "COMPLETED" else None
            return JobReceipt(
                provider="openquantum",
                provider_job_id=job_id,
                status=status,
                device_id=device_id,
                cost=None,
                shots=job.get("shots") if job else shots,
                timestamps={"createdAt": job.get("submitted_at")},
                results={"measurementCounts": counts} if counts else None,
                metadata={"execution_plan_id": PRIVATE_PLAN_ID},
            )

        body = self._wait_for_completed_proof(job_id)
        status = _map_status(str(body.get("status") or ""))
        counts = None
        raw_result = None
        output_url = body.get("output_data_url")
        if status == "COMPLETED" and output_url:
            raw_result, counts = self._download_result(str(output_url))
        proof = body.get("proof") if isinstance(body.get("proof"), dict) else None
        meta: Dict[str, Any] = {
            "provider_raw_status": body.get("status"),
            "execution_plan_id": body.get("execution_plan_id") or PRIVATE_PLAN_ID,
            "message": body.get("message"),
        }
        if proof:
            meta["proof"] = proof
        return JobReceipt(
            provider="openquantum",
            provider_job_id=job_id,
            status=status,
            device_id=device_id,
            cost=None,
            shots=shots,
            timestamps={"submitted_at": body.get("submitted_at")},
            results={"measurementCounts": counts} if counts is not None else None,
            metadata=meta,
            raw_result=raw_result,
        )

    def _submit_private_job(
        self,
        circuit_data: str,
        device_id: str,
        configuration_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        upload = self._json("POST", "v1/jobs/upload", json_body={})
        upload_id = upload.get("id")
        upload_url = upload.get("url") or upload.get("upload_url")
        if not upload_id or not upload_url:
            raise RuntimeError(f"Open Quantum upload slot missing id/url: {upload}")
        put = self._session.put(
            str(upload_url),
            data=circuit_data.encode("utf-8"),
            headers={"Content-Type": "application/octet-stream"},
            timeout=self._cfg.http_timeout_s,
        )
        put.raise_for_status()

        cfg = dict(configuration_data) if isinstance(configuration_data, dict) else {}
        prep_body = {
            "organization_id": self._cfg.organization_id,
            "backend_class_id": device_id,
            "name": "sn48-openquantum-miner",
            "upload_endpoint_id": upload_id,
            "configuration_data": cfg,
            "job_subcategory_id": self._cfg.subcategory_id,
            "submitted_with": "sn48-miner",
            "input_format": "qasm",
        }
        prep = self._json("POST", "v1/jobs/prepare", json_body=prep_body)
        prep_id = str(prep.get("id") or "")
        if not prep_id:
            raise RuntimeError(f"Open Quantum prepare missing id: {prep}")
        ready = self._wait_preparation(prep_id)
        self._last_quote = ready.get("quote") if isinstance(ready.get("quote"), list) else None
        plan_id, priority_id = self._plan_from_quote(self._last_quote)
        created = self._json(
            "POST",
            "v1/jobs",
            json_body={
                "organization_id": self._cfg.organization_id,
                "job_preparation_id": prep_id,
                "execution_plan_id": plan_id,
                "queue_priority_id": priority_id,
            },
        )
        job_id = str(created.get("id") or "")
        if not job_id:
            raise RuntimeError(f"Open Quantum create job missing id: {created}")
        bt.logging.info(
            f"[openquantum] submitted PRIVATE job_id={job_id} class={device_id} plan={plan_id}"
        )
        return job_id

    def _wait_preparation(self, prep_id: str, timeout_s: float = 120.0) -> Dict[str, Any]:
        deadline = time.time() + timeout_s
        last: Dict[str, Any] = {}
        while time.time() < deadline:
            try:
                last = self._json("GET", f"v1/jobs/prepare/{prep_id}")
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 425:
                    time.sleep(0.5)
                    continue
                raise
            status = str(last.get("status") or "").lower()
            if status in ("completed", "complete"):
                return last
            if status == "failed":
                raise RuntimeError(
                    f"Open Quantum preparation failed: {last.get('message') or last}"
                )
            time.sleep(0.5)
        raise RuntimeError(f"Open Quantum preparation timed out: {prep_id}")

    def _plan_from_quote(self, quote: Optional[list]) -> Tuple[str, str]:
        plan_id = self._cfg.execution_plan_id
        priority_id = self._cfg.queue_priority_id
        if not quote:
            return plan_id, priority_id
        private = next(
            (p for p in quote if str(p.get("execution_plan_id")) == PRIVATE_PLAN_ID),
            None,
        )
        chosen = private or (quote[0] if quote else None)
        if not isinstance(chosen, dict):
            return plan_id, priority_id
        plan_id = str(chosen.get("execution_plan_id") or plan_id)
        priorities = chosen.get("queue_priorities") or []
        if priorities and isinstance(priorities, list):
            first = priorities[0]
            if isinstance(first, dict) and first.get("queue_priority_id"):
                priority_id = str(first["queue_priority_id"])
        return plan_id, priority_id

    def last_private_price(self) -> Optional[float]:
        if not self._last_quote:
            return None
        private = next(
            (p for p in self._last_quote if str(p.get("execution_plan_id")) == PRIVATE_PLAN_ID),
            None,
        )
        if not isinstance(private, dict):
            return None
        try:
            return float(private.get("price") or 0.0)
        except (TypeError, ValueError):
            return None

    def _proof_ready(self, body: Dict[str, Any]) -> bool:
        proof = body.get("proof") if isinstance(body.get("proof"), dict) else None
        if not proof:
            return False
        signature = proof.get("signature")
        statement = proof.get("statement")
        serial = proof.get("certificate_serial") or proof.get("certificate_pem")
        has_sig = isinstance(signature, str) and bool(signature)
        has_stmt = isinstance(statement, str) and bool(statement)
        has_serial = isinstance(serial, str) and bool(serial)
        return has_sig and (has_stmt or has_serial)

    def _wait_for_completed_proof(self, job_id: str, timeout_s: float = 15.0) -> Dict[str, Any]:
        """Poll until a completed job includes its proof."""
        deadline = time.time() + timeout_s
        last: Dict[str, Any] = {}
        while time.time() <= deadline:
            body = self._get_job(job_id) or {}
            last = body
            status = _map_status(str(body.get("status") or ""))
            if status != "COMPLETED":
                return body
            if self._proof_ready(body):
                return body
            time.sleep(0.5)
        bt.logging.warning(
            f"[openquantum] COMPLETED job_id={job_id} has no completion proof after {timeout_s:.0f}s"
        )
        return last

    def _get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        try:
            return self._json("GET", f"v1/jobs/{job_id}")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (404, 202):
                return None
            raise

    def _download_result(self, url: str) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        try:
            resp = self._session.get(url, timeout=self._cfg.http_timeout_s)
            resp.raise_for_status()
            raw = resp.text
            body = resp.json()
        except Exception as e:
            bt.logging.debug(f"[openquantum] result download failed: {e}")
            return None, None
        counts = None
        if isinstance(body, dict) and isinstance(body.get("measurementCounts"), dict):
            counts = body["measurementCounts"]
        elif isinstance(body, dict) and all(isinstance(k, str) for k in body.keys()):
            counts = body
        return raw, counts

    def _json(self, method: str, path: str, json_body: Optional[dict] = None) -> Dict[str, Any]:
        url = self._url(path)
        headers = self._headers()
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        resp = self._session.request(
            method,
            url,
            headers=headers,
            json=json_body,
            timeout=self._cfg.http_timeout_s,
        )
        resp.raise_for_status()
        if not resp.content:
            return {}
        try:
            data = resp.json()
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
