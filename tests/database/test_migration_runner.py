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
Tests for the generic DB migration runner (Quantum Compute).

These tests verify:
- The runner creates the schema_migrations table.
- It correctly discovers and applies numbered baseline migrations.
- It is idempotent (safe to run multiple times).
- Both validator and miner scopes participate.
- Unknown scopes are safe (no crash).
"""

import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text

from qbittensor.database.migrations.runner import MigrationRunner, run_migrations_for_db


class TestMigrationRunner:
    def test_validator_scope_creates_schema_migrations_table_and_applies_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_validator.db"
            engine = create_engine(f"sqlite:///{db_path}")

            runner = MigrationRunner(scope="validator")
            runner.run(engine)

            with engine.connect() as conn:
                tables = [r[0] for r in conn.execute(
                    text('SELECT name FROM sqlite_master WHERE type="table"')
                )]
                assert "schema_migrations" in tables

                rows = list(conn.execute(
                    text("SELECT version, description FROM schema_migrations ORDER BY version")
                ))
                assert len(rows) >= 1
                assert rows[0][0] == 1
                assert "validator" in rows[0][1].lower() or "baseline" in rows[0][1].lower()

    def test_runner_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_idempotent.db"
            engine = create_engine(f"sqlite:///{db_path}")

            runner = MigrationRunner(scope="validator")
            runner.run(engine)
            runner.run(engine)  # second run must not blow up

            with engine.connect() as conn:
                rows = list(conn.execute(text("SELECT COUNT(*) FROM schema_migrations")))
                assert rows[0][0] >= 1

    def test_miner_scope_runs_migrations_and_creates_schema_migrations_table(self):
        """Miner DBs participate in the migration system."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_miner.db"
            engine = create_engine(f"sqlite:///{db_path}")

            run_migrations_for_db(engine, "miner")

            with engine.connect() as conn:
                tables = [r[0] for r in conn.execute(
                    text('SELECT name FROM sqlite_master WHERE type="table"')
                )]
                assert "schema_migrations" in tables

                rows = list(conn.execute(
                    text("SELECT version, description FROM schema_migrations ORDER BY version")
                ))
                assert len(rows) >= 1
                assert rows[0][0] == 1
                assert "miner" in rows[0][1].lower() or "baseline" in rows[0][1].lower(
                ) or "executions" in rows[0][1].lower()

    def test_unknown_scope_is_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test_unknown.db"
            engine = create_engine(f"sqlite:///{db_path}")

            # Should not raise
            run_migrations_for_db(engine, "unknown_scope")

            with engine.connect() as conn:
                tables = [r[0] for r in conn.execute(
                    text('SELECT name FROM sqlite_master WHERE type="table"')
                )]
                # Only sqlite_master should exist (no schema_migrations for unknown)
                assert "schema_migrations" not in tables
