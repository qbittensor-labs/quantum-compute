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

from typing import Optional
import bittensor as bt


class ExecutionMetrics:

    def __init__(self, db):
        self.db = db

    def insert_job_sent(
        self, miner_hotkey: str, execution_id: str, shots: Optional[int], time_sent: str
    ) -> None:
        """
        Insert a 'execution was sent' record. If it already exists, ignore.
        time_sent is NOT NULL in schema.
        """
        sql = """
          INSERT OR IGNORE INTO execution_metrics
              (miner_hotkey, execution_id, shots, time_sent)
          VALUES (?, ?, ?, ?)
        """
        with self.db.lock:
            self.db.query_and_commit_with_values(
                sql, (miner_hotkey, execution_id, shots, time_sent)
            )
        bt.logging.debug(
            f"[execution_metrics] insert_job_sent miner={miner_hotkey} execution_id={execution_id} shots={shots}"
        )

    def update_time_received(
        self, miner_hotkey: str, execution_id: str, time_received: str
    ) -> None:
        """
        Update when we first saw a completed execution from a miner
        """
        sql = """
          UPDATE execution_metrics
             SET time_received = COALESCE(time_received, ?)
           WHERE miner_hotkey = ? AND execution_id = ?
        """
        with self.db.lock:
            self.db.query_and_commit_with_values(
                sql, (time_received, miner_hotkey, execution_id)
            )
        bt.logging.debug(
            f"[execution_metrics] update_time_received miner={miner_hotkey} execution_id={execution_id} ts={time_received}")

    def upsert_last_circuit(self, miner_hotkey: str, ts: str) -> None:
        """
        Track the last circuit timestamp per miner
        """
        sql = """
          INSERT OR REPLACE INTO last_circuit (miner_hotkey, timestamp)
          VALUES (?, ?)
        """
        with self.db.lock:
            self.db.query_and_commit_with_values(sql, (miner_hotkey, ts))
        bt.logging.trace(
            f"[execution_metrics] upsert_last_circuit miner={miner_hotkey} ts={ts}"
        )
