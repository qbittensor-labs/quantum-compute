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

from typing import Any, Dict
from enum import Enum
from pydantic import BaseModel

from qbittensor.miner.providers.base import JobHandle


class UploadDataResponse(BaseModel):
    upload_url: str
    id: str


class MinerStatus(Enum):
    ONLINE = "Online"
    OFFLINE = "Offline"
    MAINTENANCE = "Maintenance"


class PatchBackendRequest(BaseModel):
    accepting_jobs: bool
    status: MinerStatus
    queue_depth: int
    metadata: Dict[str, Any]


class _TrackedJob:
    def __init__(self, execution_id: str, validator_hotkey: str, handle: JobHandle) -> None:
        self.execution_id = execution_id
        self.validator_hotkey = validator_hotkey
        self.handle = handle
        self.last_status = None  # will be set on first provider poll; telemetry reports real transitions only
        self._callback_invoked = False
