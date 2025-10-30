from __future__ import annotations

from typing import Protocol, Optional, Dict, Any, List
from pydantic import BaseModel, Field


class Device(BaseModel):
    device_id: str = Field(description="Unique device identifier on the provider")
    provider: str = Field(description="Provider key")
    vendor: Optional[str] = Field(default=None, description="Hardware vendor name if distinct from provider")
    device_type: str = Field(description="QPU | SIMULATOR")


class Capability(BaseModel):
    num_qubits: Optional[int] = Field(default=None, description="Total qubits available on device")
    basis_gates: Optional[List[str]] = Field(default=None, description="Supported basis/native gates")
    extras: Optional[Dict[str, Any]] = Field(default=None, description="Provider-specific capability metadata")


class JobHandle(BaseModel):
    provider_job_id: str = Field(description="Provider-side job identifier")
    device_id: str = Field(description="Target device id")


class BaseExecutionStatus(BaseModel):
    status: str = Field(description="QUEUED | RUNNING | COMPLETED | FAILED | CANCELLED | UNKNOWN")
    eta_seconds: Optional[int] = Field(default=None, description="Estimated seconds remaining for current execution")


class JobReceipt(BaseModel):
    provider: str = Field(description="Provider key")
    provider_job_id: str = Field(description="Provider-side job identifier")
    status: str = Field(description="COMPLETED | FAILED | CANCELLED | RUNNING | QUEUED | UNKNOWN")
    device_id: str = Field(description="Target device id")
    cost: Optional[float] = Field(default=None, description="Actual cost charged by the provider (if available)")
    shots: Optional[int] = Field(default=None, description="Shots for this execution if applicable")
    timestamps: Optional[Dict[str, Any]] = Field(default=None, description="Timestamps blob (createdAt, endedAt, executionDuration, etc.)")
    results: Optional[Dict[str, Any]] = Field(default=None, description="Results blob (e.g., measurementCounts, bitstrings)")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional provider metadata (queue info, compute stats)")


class MinerIdentity(BaseModel):
    """Identity for the miner's bound device."""

    device_id: Optional[str] = Field(
        default=None, description="Unique device identifier on the provider"
    )
    provider: Optional[str] = Field(
        default=None, description="Provider key"
    )
    vendor: Optional[str] = Field(
        default=None, description="Hardware vendor name if distinct from provider"
    )
    device_type: Optional[str] = Field(
        default=None, description="QPU | SIMULATOR"
    )


class AvailabilityStatus(BaseModel):
    """Live availability and queue/load indicators."""

    availability: Optional[str] = Field(
        default=None, description="ONLINE | OFFLINE | DEGRADED | MAINTENANCE"
    )
    pending_jobs: Optional[int] = Field(
        default=None, description="Number of jobs currently pending on the device"
    )
    is_available: Optional[bool] = Field(
        default=None, description="Device available for new jobs"
    )
    next_available: Optional[str] = Field(
        default=None, description="RFC3339 timestamp when device is next expected to be available"
    )
    status_msg: Optional[str] = Field(
        default=None, description="Provider-supplied status message"
    )


class Capabilities(BaseModel):
    """capability snapshot."""

    num_qubits: Optional[int] = Field(
        default=None, description="Total qubits available on device"
    )
    basis_gates: Optional[List[str]] = Field(
        default=None, description="Supported basis/native gates"
    )
    extras: Optional[Dict[str, Any]] = Field(
        default=None, description="Provider-specific capability metadata"
    )

  
class ProviderAdapter(Protocol):
    """interface for QPU providers."""

    def list_devices(self) -> List[Device]:
        ...

    def list_capabilities(self) -> List[Capability]:
        ...

    def get_capability(self, device_id: Optional[str] = None) -> Optional[Capability]:
        ...

    def submit(self, circuit_data: str, device_id: Optional[str] = None, shots: Optional[int] = None) -> JobHandle:
        ...

    def poll(self, handle: JobHandle) -> BaseExecutionStatus:
        ...

    def cancel(self, handle: JobHandle) -> None:
        ...

    def get_job_receipt(self, handle: JobHandle) -> JobReceipt:
        ...

    def get_availability(self, device_id: Optional[str] = None) -> Optional[AvailabilityStatus]:
        ...

    def get_pricing(self, device_id: Optional[str] = None) -> Optional[Dict[str, float]]:
        ...


