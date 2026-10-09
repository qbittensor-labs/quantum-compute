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
DB connection and directory resolution helper for Quantum Compute.

Modeled on enigma-staging's qbittensor/database/db_connection.py for alignment.
Provides robust resolution of the data directory (handles editable installs,
multiple checkouts, argv[0], env overrides) and a DBConnection class.

Quantum uses a simpler raw-SQL DatabaseManager for its query API, so this
primarily supplies the resolver + an optional higher-level connection helper.
"""

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine

from .migrations.runner import run_migrations_for_db


def _package_fallback_project_root() -> Path:
    """Fallback using the location of this module inside the installed qbittensor package."""
    return Path(__file__).resolve().parents[2]


def _first_project_root_walking_up(start: Path) -> Path | None:
    """First ancestor of ``start`` (including ``start``) that contains ``qbittensor/database/``.

    Used to find the correct source checkout for data/ when running neurons/CLIs
    from a different tree or with multiple editable installs.
    """
    here = start.resolve()
    for base in (here, *here.parents):
        if (base / "qbittensor" / "database").is_dir():
            return base
    return None


def _project_root_from_argv0() -> Path | None:
    if not sys.argv:
        return None
    raw = Path(sys.argv[0])
    try:
        resolved = raw.resolve()
    except (OSError, RuntimeError):
        resolved = None
    if resolved and resolved.exists():
        start = resolved if resolved.is_dir() else resolved.parent
        root = _first_project_root_walking_up(start)
        if root is not None:
            return root
    try:
        import __main__
        if hasattr(__main__, "__file__") and __main__.__file__:
            main_path = Path(__main__.__file__)
            if main_path.exists():
                start = main_path if main_path.is_dir() else main_path.parent
                root = _first_project_root_walking_up(start)
                if root is not None:
                    return root
    except Exception:
        pass
    return None


def _project_root_from_cwd() -> Path | None:
    return _first_project_root_walking_up(Path.cwd())


def _resolve_db_dir(data_dir_override: str | None = None) -> Path:
    """``<project-root>/data`` where project root is detected structurally."""
    if data_dir_override:
        return Path(data_dir_override).expanduser().resolve()

    data_dir = os.environ.get("DATA_DIR") or os.environ.get("NEURON_DATA_DIR")
    if data_dir:
        return Path(data_dir).expanduser().resolve()

    root = _project_root_from_argv0() or _project_root_from_cwd()
    if root is not None:
        return (root / "data").resolve()

    return _package_fallback_project_root() / "data"


class DBConnection:
    """Higher-level DB connection helper (aligned with enigma).

    For Quantum Compute, this primarily handles resolution and migration running.
    The low-level query API is still provided by DatabaseManager for compatibility.
    """

    def __init__(self, database_name_prefix: str, hotkey: str, data_dir: str | None = None):
        self.database_name_prefix = database_name_prefix
        DB_DIR = _resolve_db_dir(data_dir_override=data_dir)
        # Use full hotkey to match existing quantum naming: validator_<full>.db
        DB_NAME = f"{database_name_prefix}_{hotkey}.db"
        os.makedirs(DB_DIR, exist_ok=True)

        self.DB_PATH = str(DB_DIR / DB_NAME)
        self.DATABASE_URL = f"sqlite:///{self.DB_PATH}"

        self._ensure_database()

    def _ensure_database(self):
        """Ensure DB file + run migrations for the appropriate scope."""
        engine = create_engine(self.DATABASE_URL, echo=False)
        scope = None
        if self.database_name_prefix.startswith("validator"):
            scope = "validator"
        elif self.database_name_prefix.startswith("miner"):
            scope = "miner"

        if scope:
            run_migrations_for_db(engine, scope)

    def get_raw_connection(self):
        """Return a raw sqlite3 connection for compatibility with existing code."""
        import sqlite3
        return sqlite3.connect(self.DB_PATH)
