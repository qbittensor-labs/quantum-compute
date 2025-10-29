from __future__ import annotations

from typing import Any, Dict
from enum import Enum
from pydantic import BaseModel

from qbittensor.miner.providers.base import JobHandle


class UploadDataResponse(BaseModel):
    upload_url: str
    id: str


class Pricing(BaseModel):
    per_task: float | None
    per_shot: float | None
    per_minute: float | None


class MinerStatus(Enum):
    ONLINE = "Online"
    OFFLINE = "Offline"
    MAINTENANCE = "Maintenance"


class PatchBackendRequest(BaseModel):
    accepting_jobs: bool
    status: MinerStatus
    queue_depth: int
    metadata: Dict[str, Any]
    pricing: Pricing


class _TrackedJob:
    def __init__(self, execution_id: str, validator_hotkey: str, handle: JobHandle) -> None:
        self.execution_id = execution_id
        self.validator_hotkey = validator_hotkey
        self.handle = handle
        self.last_status = "QUEUED"
        self._callback_invoked = False


