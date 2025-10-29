from __future__ import annotations

import time
from typing import Dict, List, Optional
from pydantic import BaseModel

from .base import ProviderAdapter, Device, Capability, JobHandle, BaseExecutionStatus, JobReceipt, AvailabilityStatus


class _InMemoryJob(BaseModel):
    execution_id: str
    device_id: str
    submitted_at: float
    duration_s: float
    status: str
    shots: Optional[int] = None


class MockProviderAdapter(ProviderAdapter):
    """mock provider adapter."""

    def __init__(self) -> None:
        self._devices: List[Device] = [
            Device(device_id="mock_qpu_1", provider="mock", vendor="mockvendor", device_type="QPU"),
            Device(device_id="mock_sim_1", provider="mock", vendor="mockvendor", device_type="SIMULATOR"),
        ]
        self._caps: Dict[str, Capability] = {
            "mock_qpu_1": Capability(num_qubits=16, basis_gates=["x", "y", "z", "cx"]),
            "mock_sim_1": Capability(num_qubits=32, basis_gates=["x", "y", "z", "cx", "rx", "ry", "rz"]),
        }
        self._jobs: Dict[str, _InMemoryJob] = {}
        self._id_counter = 1

    def list_capabilities(self) -> List[Capability]:
        return [self._caps[d.device_id] for d in self._devices]

    def get_capability(self, device_id: Optional[str] = None) -> Optional[Capability]:
        did = device_id or self._devices[0].device_id
        return self._caps.get(did)

    def list_devices(self) -> List[Device]:
        return list(self._devices)

    def submit(self, circuit_data: str, device_id: Optional[str] = None, shots: Optional[int] = None) -> JobHandle:
        target = device_id or self._devices[0].device_id
        execution_id = f"job_{self._id_counter}"
        self._id_counter += 1
        now = time.time()
        duration_s = max(1.0, min(5.0, len(circuit_data) / 1000.0))
        self._jobs[execution_id] = _InMemoryJob(
            execution_id=execution_id, device_id=target, submitted_at=now, duration_s=duration_s, status="QUEUED"
        )
        return JobHandle(provider_job_id=execution_id, device_id=target)

    def poll(self, handle: JobHandle) -> BaseExecutionStatus:
        job = self._jobs.get(handle.provider_job_id)
        if not job:
            return BaseExecutionStatus(status="UNKNOWN", eta_seconds=None)
        now = time.time()
        elapsed = now - job.submitted_at
        if elapsed < 0.2:
            job.status = "QUEUED"
        elif elapsed < job.duration_s:
            job.status = "RUNNING"
        else:
            job.status = "COMPLETED"
        remaining = max(0, int(job.duration_s - max(0, elapsed)))
        return BaseExecutionStatus(status=job.status, eta_seconds=remaining if job.status != "COMPLETED" else 0)

    def cancel(self, handle: JobHandle) -> None:
        job = self._jobs.get(handle.provider_job_id)
        if job and job.status not in ("COMPLETED", "FAILED", "CANCELLED"):
            job.status = "CANCELLED"

    def get_job_receipt(self, handle: JobHandle) -> JobReceipt:
        job = self._jobs.get(handle.provider_job_id)
        cost = None
        status = "UNKNOWN"
        device_id = handle.device_id
        if job:
            status = job.status
            device_id = job.device_id
            if job.status == "COMPLETED":
                cost = 0.001 * max(1, int(job.duration_s))
        return JobReceipt(
            provider="mock",
            provider_job_id=handle.provider_job_id,
            status=status,
            device_id=device_id,
            cost=cost,
            shots=job.shots if job and job.shots is not None else 1000,
            timestamps={
                "createdAt": job.submitted_at if job else None,
                "endedAt": (job.submitted_at + job.duration_s) if job and job.status == "COMPLETED" else None,
                "executionDuration": job.duration_s if job else None,
            },
            results={
                "measurementCounts": {"00": 500, "11": 500} if status == "COMPLETED" else None
            },
            metadata={"queueDepth": None, "queuePosition": None, "mock": True},
        )

    def get_availability(self, device_id: Optional[str] = None) -> Optional[AvailabilityStatus]:
        target = device_id or self._devices[0].device_id
        pending = len([j for j in self._jobs.values() if j.device_id == target and j.status in ("QUEUED", "RUNNING")])
        return AvailabilityStatus(
            availability="ONLINE",
            pending_jobs=pending,
            is_available=True,
            next_available=None,
            status_msg="mock"
        )

    def get_pricing(self, device_id: Optional[str] = None) -> Optional[Dict[str, float]]:
        return {"perTask": 0.03, "perShot": 0.001, "perMinute": 0.08}


