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

from typing import Any
from pydantic import BaseModel


class ComputeRequest(BaseModel):
    execution_id: str
    input_data_url: str
    shots: int
    configuration_data: dict[str, Any]
    backend_class_id: str | None = None

    @classmethod
    def from_api_response(cls, api_response: dict[str, Any]) -> 'ComputeRequest':
        """Create ComputeRequest from API response with field name mapping."""
        cfg = api_response.get("configuration_data") or {}
        if not isinstance(cfg, dict):
            cfg = {}
        raw_shots = cfg.get("shots")
        try:
            shots = int(raw_shots) if raw_shots is not None else 0
        except (TypeError, ValueError):
            shots = 0
        return cls(
            execution_id=api_response["execution_id"],
            input_data_url=api_response["input_data_url"],
            shots=shots,
            configuration_data=cfg,
            backend_class_id=api_response.get("backend_class_id"),
        )

    def __repr__(self):
        return (
            f"ComputeRequest(execution_id: {self.execution_id}, shots: {self.shots}, "
            f"configuration_data: {self.configuration_data}, input_data_url: {self.input_data_url})"
        )

    def __str__(self):
        return (
            f"ComputeRequest(execution_id: {self.execution_id}, shots: {self.shots}, "
            f"configuration_data: {self.configuration_data}, input_data_url: {self.input_data_url})"
        )

    def __eq__(self, other) -> bool:
        if isinstance(other, ComputeRequest):
            return self.execution_id == other.execution_id
        return False
