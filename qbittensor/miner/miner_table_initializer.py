from pkg.database.database_manager import DatabaseManager
from pkg.database.table_initializer import TableInitializer


class MinerTableInitializer(TableInitializer):
    def __init__(self, database_manager: DatabaseManager):
        super().__init__(database_manager)

    def create_tables(self) -> None:
        """Create all miner tables"""
        self._create_executions_table()

    def _create_executions_table(self) -> None:
        """Create table for provider receipts/results for completed jobs"""
        self.database_manager.query_and_commit('''
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
        self.database_manager.query_and_commit('''
            CREATE INDEX IF NOT EXISTS idx_completed_at ON executions(completed_at)
        ''')
