from datetime import datetime, timezone

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

def timestamp() -> datetime:
    """Get the current timestamp"""
    return datetime.now(timezone.utc)

def timestamp_str() -> str:
    """Get the current timestamp as a string"""
    return timestamp().strftime(TIMESTAMP_FORMAT)

def timestamp_iso() -> str:
    """Get the current timestamp in ISO 8601 format"""
    return timestamp().isoformat()
