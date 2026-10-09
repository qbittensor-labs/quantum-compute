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

import pytest
from datetime import timedelta, datetime
from time import sleep
import threading

from qbittensor.database.database_manager import DatabaseManager
from qbittensor.utils.timer import Timer
from qbittensor.utils.time import timestamp
from tests.miner.constants import VALIDATOR_TEST_DB_NAME
from tests.validator.utils import cleanup_db, setup_db


@pytest.fixture
def db() -> DatabaseManager:
    database_manager: DatabaseManager = setup_db()
    return database_manager


@pytest.fixture(scope="function", autouse=True)
def teardown():
    """Runs once after each test in this session."""
    yield  # tests run here
    # cleanup logic after all tests
    db_manager = DatabaseManager(VALIDATOR_TEST_DB_NAME)
    cleanup_db(db_manager)


def test_run_on_start_true(db) -> None:
    """Test that the run on start True runs right away"""
    table: str = "last_circuit"
    values: tuple = ("test_hk",)

    def _run() -> None:
        db.query_and_commit_with_values(f"INSERT OR IGNORE INTO {table} (miner_hotkey) VALUES(?)", values)

    timer: Timer = Timer(timeout=timedelta(seconds=10), run=_run, run_on_start=True)
    timer.check_timer()
    conditions: str = "miner_hotkey=?"
    row_exists: bool = db.row_exists(table, conditions, values)
    assert row_exists


def test_run_on_start_false(db) -> None:
    """Test that run on start False doesn't run right away"""
    table: str = "last_circuit"
    values: tuple = ("test_hk",)

    def _run() -> None:
        db.query_and_commit_with_values(f"INSERT OR IGNORE INTO {table} (miner_hotkey) VALUES(?)", values)

    timer: Timer = Timer(timeout=timedelta(seconds=3), run=_run)
    timer.check_timer()

    conditions: str = "miner_hotkey=?"
    row_exists: bool = db.row_exists(table, conditions, values)
    assert not row_exists

    sleep(3)

    timer.check_timer()
    row_exists: bool = db.row_exists(table, conditions, values)
    assert row_exists


def test_run_in_thread(db) -> None:
    """Test that running with a thread works"""
    def _run() -> None:
        sleep(10)

    def is_thread_running(thread_name: str) -> bool:
        return any(thread.name == thread_name and thread.is_alive()
                   for thread in threading.enumerate())

    thread_name = "TEST THREAD NAME"
    timer: Timer = Timer(
        timeout=timedelta(
            minutes=10),
        run=_run,
        run_on_start=True,
        run_in_thread=True,
        thread_name=thread_name)
    timer.check_timer()

    assert is_thread_running(thread_name)


def test_should_start() -> None:
    """Test should start logic"""
    def _run() -> None:
        sleep(10)

    timer: Timer = Timer(timeout=timedelta(seconds=3), run=_run, run_on_start=False, run_in_thread=True)

    assert not timer._should_start()  # Assert that it shouldn't start yet
    sleep(3)  # sleep for timeout duration
    assert timer._should_start()  # Assert that it should start


def test_timer_reset() -> None:
    """Test internal timer reset"""
    def _run() -> None:
        sleep(10)

    initial_timestamp: datetime = timestamp()
    timer: Timer = Timer(timeout=timedelta(seconds=3), run=_run, run_on_start=False, run_in_thread=True)

    time_diff: timedelta = initial_timestamp - timer._timer  # Calculate time diff
    assert time_diff < timedelta(seconds=1)  # Assert that the internal _timer field was not reset yet

    now: datetime = timestamp()
    timer.check_timer()  # Call to check_timer(). This should reset internal _timer field
    time_diff: timedelta = now - timer._timer  # Calculate time diff
    assert time_diff < timedelta(seconds=1)  # Assert that the internal _timer field was reset
