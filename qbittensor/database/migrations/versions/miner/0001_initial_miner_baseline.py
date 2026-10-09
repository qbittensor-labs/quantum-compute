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

"""
Initial baseline migration for the miner database.

Creates the core 'executions' table used by the miner runtime to track
provider jobs and their lifecycle.
"""

VERSION = 1
DESCRIPTION = "Initial miner baseline: executions table"


def upgrade(engine, telemetry_service=None):
    """Create executions table and supporting index."""
    # Use raw connection for CREATE (works alongside SQLAlchemy metadata)
    with engine.connect() as conn:
        conn.exec_driver_sql('''
            CREATE TABLE IF NOT EXISTS executions (
                execution_id TEXT PRIMARY KEY,
                upload_data_id TEXT,
                validator_hotkey TEXT,
                provider TEXT,
                provider_job_id TEXT,
                device_id TEXT,
                status TEXT CHECK( status IN ('Pending', 'Queued', 'Running', 'Completed', 'Failed') ),
                errorMessage TEXT,
                cost REAL,
                shots INTEGER,
                timestamp DATETIME,
                timestamps_json TEXT,
                metadata_json TEXT,
                completed_at DATETIME
            )
        ''')
        conn.exec_driver_sql('''
            CREATE INDEX IF NOT EXISTS idx_completed_at ON executions(completed_at)
        ''')
        conn.commit()


def downgrade(engine):
    """Downgrade not supported for baseline."""
    pass
