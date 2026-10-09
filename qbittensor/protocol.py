# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
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

"""
Protocol for Quantum
"""
from __future__ import annotations
from qbittensor import bt_compat  # noqa: F401 — install Synapse shim
import bittensor as bt
from pydantic import Field, BaseModel
from typing import Optional, Any

from qbittensor.validator.utils.execution_status import ExecutionStatus

# Re-export: miners check synapse.execution_id against this to know there is
# no new circuit and they should only return finished executions.
from qbittensor.constants import COLLECT_SYNAPSE_ID as COLLECT_SYNAPSE_ID  # noqa: F401


class ExecutionData(BaseModel):
    """Data associated with the completion of a execution. This comes from the Miner's database."""
    execution_id: str = Field(
        description="ID for the execution"
    )
    shots: int = Field(
        description="Number of shots for the execution"
    )
    upload_data_id: Optional[str] = Field(
        description="ID for the uploaded data. Required if the execution completed successfully"
    )
    execution_data: Optional[object] = Field(
        description="Data relating to the provider's execution of the request. This could be an internal job id."
    )
    status: ExecutionStatus = Field(
        description="Status of the execution"
    )
    errorMessage: Optional[str] = Field(
        default=None, description="Error message if something went wrong"
    )


class CircuitSynapse(bt.Synapse):
    """Common metadata carried by every circuit-related synapse."""

    execution_id: str = Field(
        description="The execution ID for this request"
    )

    shots: int = Field(
        description="The number of shots requested"
    )

    configuration_data: dict[str, Any] = Field(
        description="The configuration data for this request"
    )

    backend_class_id: Optional[str] = Field(
        default=None,
        description="Backend class for this circuit",
    )

    input_data_url: str = Field(
        description="The URL where the input data (e.g., QASM) can be found"
    )

    success: bool = Field(
        default=False, description="Set by the miner when it handled the request"
    )

    error_message: Optional[str] = Field(
        default=None, description="Error message if something went wrong"
    )

    last_circuit: str = Field(
        description="The timestamp of the last circuit received from the miner this synapse is sent to"
    )

    # flag for rate limiting
    rate_limited: Optional[bool] = Field(
        default=False,
        description="Flag the miner to set to indicate that this request was ignored due to rate limiting")

    execution_status: ExecutionStatus = Field(
        default=ExecutionStatus.PENDING, description="The new status for this execution"
    )

    # list of finished executions
    finished_executions: list[ExecutionData] = Field(
        default_factory=list, description="List of finished execution data"
    )

    active_executions: list[ExecutionData] = Field(
        default_factory=list,
        description="In-flight executions (Pending/Queued/Running) for validator heartbeat",
    )

    capabilities: list[str] = Field(
        default_factory=list,
        description="backend_class.short_code values this miner accepts. Empty = not placeable.",
    )
