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

from __future__ import annotations

"""
Generic, versioned database migration runner for Quantum Compute (SN 48).

Modeled on the Enigma pattern for alignment:
- Simple and self-contained (no external Alembic).
- Safe and idempotent to run on every startup.
- Separate migration sets for "validator" and "miner".
- Easy to evolve the schema over time.
"""

import importlib
import logging
import pkgutil
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import Column, Integer, String, DateTime, text, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Migration metadata table (created automatically if missing)
# --------------------------------------------------------------------------- #

MigrationBase = declarative_base()


class SchemaMigration(MigrationBase):
    """Tracks which migrations have been applied."""

    __tablename__ = "schema_migrations"

    version = Column(Integer, primary_key=True)
    description = Column(String(255), nullable=False)
    applied_at = Column(DateTime, nullable=False, server_default=func.now())


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Migration:
    version: int
    description: str
    upgrade: Callable[[Engine], None]
    downgrade: Callable[[Engine], None] | None = None


# --------------------------------------------------------------------------- #
# Core runner
# --------------------------------------------------------------------------- #


class MigrationRunner:
    """
    Generic migration runner.

    Usage:
        runner = MigrationRunner(scope="validator")
        runner.run(engine)
    """

    def __init__(self, scope: str = "validator"):
        """
        Args:
            scope: Logical scope of migrations ("validator" or "miner").
        """
        self.scope = scope.lower()
        self._migrations: list[Migration] | None = None

    def _get_migrations_package(self) -> str:
        if self.scope == "validator":
            return "qbittensor.database.migrations.versions.validator"
        elif self.scope == "miner":
            return "qbittensor.database.migrations.versions.miner"
        else:
            raise ValueError(f"Unknown migration scope: {self.scope}")

    def _discover_migrations(self) -> list[Migration]:
        """Dynamically import all migration modules for this scope and collect them."""
        package_name = self._get_migrations_package()
        migrations: list[Migration] = []

        try:
            package = importlib.import_module(package_name)
        except ModuleNotFoundError:
            logger.debug(f"No migration package found for scope '{self.scope}' at {package_name}")
            return []

        for module_info in pkgutil.iter_modules(package.__path__):
            if not module_info.name[0].isdigit():
                continue  # Only numbered migration files

            full_name = f"{package_name}.{module_info.name}"
            mod = importlib.import_module(full_name)

            version = getattr(mod, "VERSION", None)
            description = getattr(mod, "DESCRIPTION", module_info.name)
            upgrade = getattr(mod, "upgrade", None)
            downgrade = getattr(mod, "downgrade", None)

            if version is None or upgrade is None:
                logger.warning(f"Skipping invalid migration module: {full_name}")
                continue

            migrations.append(
                Migration(
                    version=int(version),
                    description=str(description),
                    upgrade=upgrade,
                    downgrade=downgrade,
                )
            )

        migrations.sort(key=lambda m: m.version)
        return migrations

    def _ensure_migrations_table(self, engine: Engine) -> None:
        """Create the schema_migrations table if it does not exist."""
        MigrationBase.metadata.create_all(bind=engine, tables=[SchemaMigration.__table__])

    def _get_applied_versions(self, engine: Engine) -> set[int]:
        """Return the set of already-applied migration versions."""
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT version FROM schema_migrations ORDER BY version")
            )
            return {row[0] for row in result}

    def run(self, engine: Engine) -> None:
        """
        Run all pending migrations for this scope in order.
        Safe to call multiple times.
        """
        self._ensure_migrations_table(engine)
        applied = self._get_applied_versions(engine)

        if self._migrations is None:
            self._migrations = self._discover_migrations()

        pending = [m for m in self._migrations if m.version not in applied]

        if not pending:
            logger.debug(f"[{self.scope}] Database is up to date (no pending migrations).")
            return

        logger.info(f"[{self.scope}] Running {len(pending)} pending migration(s)...")

        Session = sessionmaker(bind=engine)

        for migration in pending:
            logger.info(f"[{self.scope}] Applying migration {migration.version}: {migration.description}")

            try:
                migration.upgrade(engine)

                with Session() as session:
                    session.add(
                        SchemaMigration(
                            version=migration.version,
                            description=migration.description,
                        )
                    )
                    session.commit()

                logger.info(f"[{self.scope}] Successfully applied migration {migration.version}")

            except Exception as e:
                logger.exception(f"[{self.scope}] FAILED to apply migration {migration.version}: {e}")
                raise

        logger.info(f"[{self.scope}] All migrations completed successfully.")


def run_migrations_for_db(engine: Engine, scope: str) -> None:
    """
    Run migrations for the given scope ("miner" or "validator").
    """
    if scope in ("validator", "miner"):
        runner = MigrationRunner(scope=scope)
        runner.run(engine)
    else:
        logger.debug(f"No migration scope defined for '{scope}'")
