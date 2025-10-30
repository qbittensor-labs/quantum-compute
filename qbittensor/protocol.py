"""
Protocol for Quantum
"""
from __future__ import annotations
import bittensor as bt
from pydantic import Field, BaseModel
from typing import Optional, Any

from qbittensor.validator.utils.execution_status import ExecutionStatus

# This is used so that miners know that there is no new circuit in the synapse, and they should just send back their finished executions
COLLECT_SYNAPSE_ID = "_collect_only"


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
    
    input_data_url: str = Field(
        description="The URL where the input data (e.g., QASM) can be found"
    )

    success: bool = Field(
        default=False, description="Set by the miner so that vali knows it responded"
    )
    
    error_message: Optional[str] = Field(
        default=None, description="Error message if something went wrong"
    )

    last_circuit: str = Field(
        description="The timestamp of the last circuit received from the miner this synapse is sent to"
    )

    # flag for rate limiting
    rate_limited: Optional[bool] = Field(
        default=False, description="Flag the miner to set to indicate that this request was ignored due to rate limiting"
    )
    
    execution_status: ExecutionStatus = Field(
        default=ExecutionStatus.PENDING, description="The new status for this execution"
    )

    # list of finished executions
    finished_executions: list[ExecutionData] = Field(
        default_factory=list, description="List of finished execution data"
    )
