from typing import Any
from pydantic import BaseModel

class ComputeRequest(BaseModel):
    execution_id: str
    input_data_url: str
    shots: int
    configuration_data: dict[str, Any]
    
    @classmethod
    def from_api_response(cls, api_response: dict[str, Any]) -> 'ComputeRequest':
        """Create ComputeRequest from API response with field name mapping."""
        return cls(
            execution_id=api_response["execution_id"],
            input_data_url=api_response["input_data_url"],
            shots=api_response["shots"],
            configuration_data=api_response["configuration_data"]
        )
    
    def __repr__(self):
        return f"ComputeRequest(execution_id: {self.execution_id}, shots: {self.shots}, configuration_data: {self.configuration_data}, input_data_url: {self.input_data_url})"

    def __str__(self):
        return f"ComputeRequest(execution_id: {self.execution_id}, shots: {self.shots}, configuration_data: {self.configuration_data}, input_data_url: {self.input_data_url})"
    
    def __eq__(self, other) -> bool:
        if isinstance(other, ComputeRequest):
            return self.execution_id == other.execution_id
        return False
    