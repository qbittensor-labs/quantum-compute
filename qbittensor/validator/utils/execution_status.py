from enum import Enum

class ExecutionStatus(str, Enum):
    """Enum for execution status"""
    PENDING = "Pending"
    QUEUED = "Queued"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"
