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
            f"[execution_metrics] update_time_received miner={miner_hotkey} execution_id={execution_id} ts={time_received}"
        )

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
