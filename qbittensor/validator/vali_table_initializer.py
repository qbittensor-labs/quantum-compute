from pkg.database.database_manager import DatabaseManager
from pkg.database.table_initializer import TableInitializer


class ValidatorTableInitializer(TableInitializer):
    def __init__(self, database_manager: DatabaseManager):
        super().__init__(database_manager)

    def create_tables(self) -> None:
        """Create all validator tables"""
        self._create_last_circuit_table()
        self._create_active_miners_table()
        self._create_executions_table()
        
    def _create_successful_jobs_table(self) -> None:
        """Create table for counting successful jobs"""
        self.database_manager.query_and_commit('''
            CREATE TABLE IF NOT EXISTS successful_job (
                miner_hotkey TEXT PRIMARY KEY
                execution_id,
                created_at DATETIME
            )                                
        ''')
        self.database_manager.query_and_commit("CREATE INDEX IF NOT EXISTS execution_id_idx ON successful_job (execution_id)")

    def _create_last_circuit_table(self) -> None:
        """Create table to maintain the last circuit update from each miner"""
        self.database_manager.query_and_commit('''
            CREATE TABLE IF NOT EXISTS last_circuit (
                miner_hotkey TEXT PRIMARY KEY,
                timestamp DATETIME
            )
        ''')

    def _create_active_miners_table(self) -> None :
        """Create table for tracking active miners, handling dereg"""
        self.database_manager.query_and_commit('''
            CREATE TABLE IF NOT EXISTS active_miners(
                hotkey TEXT PRIMARY KEY,
                uid INTEGER,                                               
                timestamp DATETIME
            )
        ''')

    def _create_executions_table(self) -> None:
        """Per-miner per-execution data"""
        self.database_manager.query_and_commit('''
            CREATE TABLE IF NOT EXISTS execution_metrics (
                miner_hotkey TEXT,
                execution_id TEXT,
                shots INTEGER,
                time_sent DATETIME NOT NULL,
                time_received DATETIME,
                PRIMARY KEY (miner_hotkey, execution_id)
            )
        ''')
