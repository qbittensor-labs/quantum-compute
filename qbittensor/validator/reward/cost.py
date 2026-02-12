from datetime import timedelta, datetime, timezone
import bittensor as bt
from typing import List, Tuple
import requests

from pkg.database.database_manager import DatabaseManager 
from qbittensor.utils.Timer import Timer
from qbittensor.utils.request.RequestManager import RequestManager

MAX_DATA_AGE: timedelta = timedelta(days=30)

class CostConfirmation:
    def __init__(self, database_manager: DatabaseManager, request_manager: RequestManager):
        self.database_manager: DatabaseManager = database_manager
        self.request_manager: RequestManager = request_manager
        self.timer: Timer = Timer(timedelta(minutes=30), self._run, run_on_start=True)
        
    def _run(self):
        bt.logging.info("💰 Running cost confirmation process.")
        rows: List[Tuple[str, str]] = self._get_rows()
        bt.logging.info(f"💰 Found {len(rows)} rows that need cost confirmation.")
        for miner_hotkey, execution_id in rows:
            cost: requests.Response = self._get_cost(miner_hotkey, execution_id)
            self._handle_cost_response(cost, miner_hotkey, execution_id)
        self._clean_out_table()
        
    def _handle_cost_response(self, response: requests.Response, miner_hotkey: str, execution_id: str) -> None:
        """Handle the response from the cost endpoint. If successful, update the database with the cost."""
        if response.status_code == 200:
            cost_data: dict = response.json()
            cost: int = cost_data.get("cost", 0)
            self._update_cost_in_db(miner_hotkey, execution_id, cost)
        elif response.status_code == 202:
            return
        elif response.status_code == 404:
            self._drop_row(miner_hotkey, execution_id)
        else:
            bt.logging.error(f"Failed to get cost for miner {miner_hotkey} and execution {execution_id}. Unexpected status code: {response.status_code}")
        
    def _drop_row(self, miner_hotkey: str, execution_id: str) -> None:
        """Drop a row from the database."""
        query: str = """
            DELETE FROM successful_job
            WHERE miner_hotkey = ? AND execution_id = ?
        """
        values: tuple = (miner_hotkey, execution_id)
        self.database_manager.query_and_commit_with_values(query, values)
        
    def _update_cost_in_db(self, miner_hotkey: str, execution_id: str, cost: float) -> None:
        """Update the cost of a successful job in the database."""
        query: str = """
            UPDATE successful_job
            SET cost = ?
            WHERE miner_hotkey = ? AND execution_id = ?
        """
        values: tuple = (cost, miner_hotkey, execution_id)
        self.database_manager.query_and_commit_with_values(query, values)
        
    def _get_cost(self, miner_hotkey: str, execution_id: str) -> requests.Response:
        """Get the cost of a successful job"""
        endpoint: str = f"executions/{execution_id}/cost"
        params: dict = {"miner_hotkey": miner_hotkey}
        return self.request_manager.get(endpoint, params=params, ignore_codes=[404])
        
    def _get_rows(self) -> List[Tuple[str, str]]:
        """Get rows that need cost confirmation."""
        query: str = self._get_data_query()
        return self.database_manager.query(query)
        
    def _get_data_query(self) -> str:
        """Get the SQL query to retrieve rows that don't have cost data yet"""
        return """
            SELECT miner_hotkey, execution_id FROM successful_job
            WHERE cost IS NULL
        """
        
    def _clean_out_table(self) -> None:
        """Delete all rows from the successful_job table where created_at is older than x"""
        min_time: datetime = datetime.now(timezone.utc) - MAX_DATA_AGE
        count_query: str = """SELECT COUNT(*) FROM successful_job WHERE created_at < ?"""
        count_result: List[Tuple[int]] = self.database_manager.query_with_values(count_query, (min_time,))
        count: int = count_result[0][0] if count_result else 0
        bt.logging.info(f"🗑️ Cleaning out successful_job table. Found {count} rows older than {min_time}.")
        query: str = """DELETE FROM successful_job WHERE created_at < ?"""
        values: tuple = (min_time,)
        self.database_manager.query_and_commit_with_values(query, values)