from pkg.database.database_manager import DatabaseManager
from qbittensor.validator.vali_table_initializer import ValidatorTableInitializer
from tests.miner.constants import VALIDATOR_TEST_DB_NAME

def setup_db() -> DatabaseManager:
    db_manager = DatabaseManager(VALIDATOR_TEST_DB_NAME)
    ValidatorTableInitializer(db_manager).create_tables()
    return db_manager

def cleanup_db(database_manager: DatabaseManager):
    database_manager = DatabaseManager(VALIDATOR_TEST_DB_NAME)
    database_manager.query_and_commit("DELETE FROM active_miners")
    database_manager.query_and_commit("DELETE FROM last_circuit")
    database_manager.query_and_commit("DELETE FROM execution_metrics")