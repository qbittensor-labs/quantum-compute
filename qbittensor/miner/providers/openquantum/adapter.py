# The MIT License (MIT)
# Copyright © 2026 qBitTensor Labs

from __future__ import annotations

from typing import Any, Dict, List, Optional

import bittensor as bt

from qbittensor.miner.providers.base import (
    AvailabilityStatus,
    BaseExecutionStatus,
    Capability,
    Device,
    JobHandle,
    JobReceipt,
)

from .config import OpenQuantumConfig
from .credits import get_remaining_credits, should_rate_limit_for_low_credits
from .jobs import JobService


class OpenQuantumAdapter:
    """Submits Open Quantum jobs and reports their status."""

    def __init__(self, config: OpenQuantumConfig | None = None) -> None:
        self._cfg = config or OpenQuantumConfig.from_env(strict=True)
        self._jobs = JobService(self._cfg)
        self._last_availability: Optional[AvailabilityStatus] = None
        self._last_credits: Optional[float] = None
        bt.logging.info(
            f"[openquantum] init dry_run={self._cfg.dry_run} "
            f"org={'set' if self._cfg.organization_id else 'unset'}"
        )

    def list_devices(self) -> List[Device]:
        return [
            Device(
                device_id="openquantum",
                provider="openquantum",
                vendor="openquantum",
                device_type="QPU",
            )
        ]

    def list_capabilities(self) -> List[Capability]:
        cap = self.get_capability("openquantum")
        return [cap] if cap else []

    def get_capability(self, device_id: Optional[str] = None) -> Optional[Capability]:
        did = device_id or "openquantum"
        return Capability(
            num_qubits=None,
            basis_gates=None,
            extras={
                "device_id": did,
                "execution_plan": "private",
                "dry_run": self._cfg.dry_run,
            },
        )

    def submit(
        self,
        circuit_data: str,
        device_id: Optional[str] = None,
        shots: Optional[int] = None,
        configuration_data: Optional[Dict[str, Any]] = None,
    ) -> JobHandle:
        target = str(device_id).strip() if device_id else ""
        if not target:
            raise RuntimeError("backend class is required")
        if not self._cfg.dry_run:
            rl = self.should_rate_limit()
            if rl is True:
                raise RuntimeError(
                    f"Open Quantum miner below OPENQUANTUM_MIN_CREDITS "
                    f"({self._cfg.min_credits}); not submitting"
                )
        job_id = self._jobs.submit(
            circuit_data=circuit_data,
            device_id=target,
            shots=shots,
            dry_run=self._cfg.dry_run,
            configuration_data=configuration_data,
        )
        return JobHandle(provider_job_id=job_id, device_id=target)

    def poll(self, handle: JobHandle) -> BaseExecutionStatus:
        status, remaining, message = self._jobs.poll(
            job_id=handle.provider_job_id, dry_run=self._cfg.dry_run
        )
        bt.logging.info(
            f"[openquantum] poll job_id={handle.provider_job_id} status={status}"
        )
        return BaseExecutionStatus(
            status=status,
            eta_seconds=remaining if status not in ("COMPLETED", "FAILED", "CANCELLED") else 0,
            message=message,
        )

    def cancel(self, handle: JobHandle) -> None:
        self._jobs.cancel(handle.provider_job_id, dry_run=self._cfg.dry_run)

    def get_job_receipt(self, handle: JobHandle) -> JobReceipt:
        return self._jobs.receipt(
            job_id=handle.provider_job_id,
            device_id=handle.device_id,
            dry_run=self._cfg.dry_run,
            shots=None,
        )

    def get_availability(self, device_id: Optional[str] = None) -> Optional[AvailabilityStatus]:
        pending = 0
        if self._cfg.dry_run:
            pending = len(
                [
                    j
                    for j in self._jobs._sim.jobs.values()
                    if j.get("status") in ("queued", "running")
                ]
            )
        below, credits = None, None
        try:
            below = should_rate_limit_for_low_credits(self._cfg)
            credits = get_remaining_credits(self._cfg)
            self._last_credits = credits
        except Exception as e:
            bt.logging.debug(f"[openquantum] credits for availability failed: {e}")
        is_available = True
        status_msg = "openquantum-private"
        if below is True:
            is_available = False
            status_msg = (
                f"low_credits ({credits} full < min {self._cfg.min_credits})"
            )
        result = AvailabilityStatus(
            availability="ONLINE",
            pending_jobs=pending,
            is_available=is_available,
            next_available=None,
            status_msg=status_msg,
        )
        self._last_availability = result
        return result

    def get_pricing(self, device_id: Optional[str] = None) -> Optional[Dict[str, float]]:
        price = self._jobs.last_private_price()
        if price is None:
            return {"perTask": 0.0, "perShot": 0.0, "perMinute": 0.0}
        return {"perTask": float(price), "perShot": 0.0, "perMinute": 0.0}

    def should_rate_limit(self) -> bool | None:
        try:
            return should_rate_limit_for_low_credits(self._cfg)
        except Exception as e:
            bt.logging.debug(f"[openquantum] credits check failed: {e}")
            return None

    def get_accepting_jobs_override(self) -> Optional[bool]:
        rl = self.should_rate_limit()
        if rl is True:
            return False
        avail = self._last_availability
        if avail is not None and avail.is_available is False:
            return False
        return None

    def should_rate_limit_request(
        self, *, shots: Optional[int], estimated_minutes: Optional[float] = None
    ) -> Optional[bool]:
        return self.should_rate_limit()

    def list_public_classes(self) -> List[str]:
        """Classes from PUBLIC_BACKEND_CLASSES. Empty means not placeable."""
        from qbittensor.miner.providers.base import list_public_classes_from_env

        return list_public_classes_from_env()
