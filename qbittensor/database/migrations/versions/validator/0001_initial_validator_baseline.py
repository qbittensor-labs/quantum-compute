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
Initial baseline migration for the validator database.

Creates the tables previously managed by ValidatorTableInitializer:
- successful_job
- last_circuit
- active_miners
- execution_metrics
"""

VERSION = 1
DESCRIPTION = "Initial validator baseline: successful_job, last_circuit, active_miners, execution_metrics"


def upgrade(engine, telemetry_service=None):
    """Create validator tables."""
    with engine.connect() as conn:
        # successful_job
        conn.exec_driver_sql('''
            CREATE TABLE IF NOT EXISTS successful_job (
                miner_hotkey TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                cost INTEGER,
                PRIMARY KEY (miner_hotkey, execution_id)
            )
        ''')

        # last_circuit
        conn.exec_driver_sql('''
            CREATE TABLE IF NOT EXISTS last_circuit (
                miner_hotkey TEXT PRIMARY KEY,
                timestamp DATETIME
            )
        ''')

        # active_miners
        conn.exec_driver_sql('''
            CREATE TABLE IF NOT EXISTS active_miners(
                hotkey TEXT PRIMARY KEY,
                uid INTEGER,
                timestamp DATETIME
            )
        ''')

        # execution_metrics
        conn.exec_driver_sql('''
            CREATE TABLE IF NOT EXISTS execution_metrics (
                miner_hotkey TEXT,
                execution_id TEXT,
                shots INTEGER,
                time_sent DATETIME NOT NULL,
                time_received DATETIME,
                PRIMARY KEY (miner_hotkey, execution_id)
            )
        ''')
        conn.commit()


def downgrade(engine):
    """Downgrade not supported for baseline."""
    pass
