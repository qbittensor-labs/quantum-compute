"""
Helper class managing connections to the SQLite database
"""
import sqlite3
from typing import Tuple
import os
from threading import RLock

data_dir = "data"

class DatabaseManager:

    def __init__(self, db_name: str):
        self.lock = RLock()  # Reentrant lock for thread safety
        os.makedirs(data_dir, exist_ok=True)  # Ensure data directory exists
        self.db_path = f'{data_dir}/{db_name}.db'  # Set db path
        db_dir = os.path.dirname(self.db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)  # Create db dir

    def query(self, query: str) -> list[tuple]:
        """
        Get all results of a query from the database
        Args:
            query: a query string

        Returns:
            All rows matching the query
        """
        cursor, db_connection = self._get_cursor()
        try:
            cursor.execute(query)
            return cursor.fetchall()
        finally:
            cursor.close()
            db_connection.close()

    def query_with_values(self, query: str, values: tuple) -> list[tuple]:
        """
        Get all results of a query from the database
        Args:
            query: a query string
            values: a tuple of values

        Returns:
            All rows matching the query
        """
        cursor, db_connection = self._get_cursor()
        try:
            cursor.execute(query, values)
            return cursor.fetchall()
        finally:
            cursor.close()
            db_connection.close()

    def query_one_with_values(self, query: str, values: tuple) -> tuple:
        """
        Get one result of a query from the database
        Args:
            query: a query string
            values: a tuple of values

        Returns:
            One row matching the query
        """
        cursor, db_connection = self._get_cursor()
        try:
            cursor.execute(query, values)
            return cursor.fetchone()
        finally:
            cursor.close()
            db_connection.close()

    def query_and_commit(self, query: str) -> None:
        """
        Use for updating the database
        Args:
            query: query string

        Returns:
            None
        """
        cursor, db_connection = self._get_cursor()
        try:
            cursor.execute(query)
            db_connection.commit()
        finally:
            cursor.close()
            db_connection.close()

    def query_and_commit_with_values(self, query: str, values: tuple) -> None:
        """
        Use for updating the database
        Args:
            query: query string
            values: a tuple of values

        Returns:
            None
        """
        cursor, db_connection = self._get_cursor()
        try:
            cursor.execute(query, values)
            db_connection.commit()
        finally:
            cursor.close()
            db_connection.close()

    def query_and_commit_many(self, query: str, values: list[tuple]) -> None:
        """
        Use for updating the database with many rows at once
        Args:
            query: query string
            values: a list of tuples

        Returns:
            None
        """
        cursor, db_connection = self._get_cursor()
        try:
            cursor.executemany(query, values)
            db_connection.commit()
        finally:
            cursor.close()
            db_connection.close()

    def row_exists(self, table: str, conditions: str, values: tuple) -> bool:
        """Check if there is a row matching the query in the database"""
        cursor, db_connection = self._get_cursor()
        query = f"SELECT 1 FROM {table} WHERE {conditions} LIMIT 1"
        try:
            cursor.execute(query, values)
            return cursor.fetchone() is not None
        finally:
            cursor.close()
            db_connection.close()

    def get_size_of_table(self, table_name: str):
        """Get the size of a table"""
        query_str = f"SELECT COUNT(*) FROM {table_name}"
        result = self.query(query_str)
        return result[0][0]

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists"""
        result = self.query(f"""SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'""")
        return len(result) > 0

    def _get_cursor(self) -> Tuple[sqlite3.Cursor, sqlite3.Connection]:
        """
        Get a cursor and connection reference from the database
        Returns:
            cursor & connection objects
        """
        db_connection = self._get_db_connection()
        cursor = db_connection.cursor()
        return cursor, db_connection

    def _get_db_connection(self) -> sqlite3.Connection:
        """
        Get a reference to the database
        Returns:
            A database connection
        """
        return sqlite3.connect(self.db_path)
