# The MIT License (MIT)
# Copyright © 2026 qBitTensor Labs

"""Validator-local record of executions this process is tracking."""

VERSION = 4
DESCRIPTION = "inflight_execution"


def upgrade(engine, telemetry_service=None):
    with engine.connect() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS inflight_execution (
                execution_id TEXT PRIMARY KEY,
                miner_hotkey TEXT NOT NULL,
                seen_at REAL NOT NULL,
                assigned INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()


def downgrade(engine):
    """Downgrade not supported."""
    pass
