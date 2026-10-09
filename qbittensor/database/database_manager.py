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
Database manager for Quantum Compute.

This is the aligned implementation (moved from pkg.database):
- Same public query/commit API for broad compatibility during transition.
- Uses versioned migrations (via the shared lightweight runner) instead of
  ad-hoc TableInitializer classes.
- Respects DATA_DIR (and --neuron.data_dir via config layer).
"""

from __future__ import annotations

import os
import sqlite3
from threading import RLock
from typing import Tuple

from sqlalchemy import create_engine

from qbittensor.database.db_connection import _resolve_db_dir
from qbittensor.database.migrations.runner import run_migrations_for_db


class DatabaseManager:
    """Thread-safe SQLite manager. Tables are now ensured via versioned migrations."""

    def __init__(self, db_name: str):
        self.lock = RLock()  # Reentrant lock for thread safety

        data_dir = str(_resolve_db_dir())
        os.makedirs(data_dir, exist_ok=True)

        self.db_path = f"{data_dir}/{db_name}.db"
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        # Determine scope for migrations from db_name convention ("validator_..." or "miner_...")
        scope = "validator" if db_name.startswith("validator") else "miner" if db_name.startswith("miner") else None

        # Run migrations (creates schema_migrations + applies baseline CREATEs)
        if scope:
            try:
                engine = create_engine(f"sqlite:///{self.db_path}", echo=False)
                run_migrations_for_db(engine, scope)
            except Exception as e:
                # Do not hard-fail startup for migration issues in early transition;
                # log and let the old IF NOT EXISTS paths (or later calls) handle it.
                import bittensor as bt
                bt.logging.warning(f"Database migration step encountered an issue for {db_name}: {e}")

    # --- Existing public API preserved for compatibility ---

    def query(self, query: str) -> list[tuple]:
        cursor, db_connection = self._get_cursor()
        try:
            cursor.execute(query)
            return cursor.fetchall()
        finally:
            cursor.close()
            db_connection.close()

    def query_with_values(self, query: str, values: tuple) -> list[tuple]:
        cursor, db_connection = self._get_cursor()
        try:
            cursor.execute(query, values)
            return cursor.fetchall()
        finally:
            cursor.close()
            db_connection.close()

    def query_one_with_values(self, query: str, values: tuple) -> tuple:
        cursor, db_connection = self._get_cursor()
        try:
            cursor.execute(query, values)
            return cursor.fetchone()
        finally:
            cursor.close()
            db_connection.close()

    def query_and_commit(self, query: str) -> None:
        cursor, db_connection = self._get_cursor()
        try:
            cursor.execute(query)
            db_connection.commit()
        finally:
            cursor.close()
            db_connection.close()

    def query_and_commit_with_values(self, query: str, values: tuple) -> None:
        cursor, db_connection = self._get_cursor()
        try:
            cursor.execute(query, values)
            db_connection.commit()
        finally:
            cursor.close()
            db_connection.close()

    def query_and_commit_many(self, query: str, values: list[tuple]) -> None:
        cursor, db_connection = self._get_cursor()
        try:
            cursor.executemany(query, values)
            db_connection.commit()
        finally:
            cursor.close()
            db_connection.close()

    def row_exists(self, table: str, conditions: str, values: tuple) -> bool:
        cursor, db_connection = self._get_cursor()
        query = f"SELECT 1 FROM {table} WHERE {conditions} LIMIT 1"
        try:
            cursor.execute(query, values)
            return cursor.fetchone() is not None
        finally:
            cursor.close()
            db_connection.close()

    def get_size_of_table(self, table_name: str):
        query_str = f"SELECT COUNT(*) FROM {table_name}"
        result = self.query(query_str)
        return result[0][0]

    def table_exists(self, table_name: str) -> bool:
        result = self.query(f"""SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'""")
        return len(result) > 0

    def _get_cursor(self) -> Tuple[sqlite3.Cursor, sqlite3.Connection]:
        db_connection = self._get_db_connection()
        cursor = db_connection.cursor()
        return cursor, db_connection

    def _get_db_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)
