from abc import ABC, abstractmethod

from pkg.database.database_manager import DatabaseManager

class TableInitializer(ABC):
    def __init__(self, database_manager: DatabaseManager) -> None:
        self.database_manager = database_manager

    @abstractmethod
    def create_tables(self) -> None:
        """Create the necessary tables"""
        pass
