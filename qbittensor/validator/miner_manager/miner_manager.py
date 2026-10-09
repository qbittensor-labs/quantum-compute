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

import threading
import bittensor as bt
from datetime import timedelta
from typing import List
from pydantic import BaseModel

from qbittensor.database.database_manager import DatabaseManager
from qbittensor.utils.timer import Timer
from qbittensor.utils.time import timestamp

from qbittensor.constants import (
    EXECUTION_METRICS_TTL_DAYS,
    TIMER_COUNTDOWN,
    TIMESTAMP_FORMAT,
)


class Miner(BaseModel):
    uid: int
    hotkey: str

    def __hash__(self):
        return hash((self.uid, self.hotkey))

    def __eq__(self, other):
        if isinstance(other, Miner):
            return self.uid == other.uid and self.hotkey == other.hotkey
        return False

    def __repr__(self) -> str:
        return f"Miner(uid={self.uid}, hotkey={self.hotkey})"

    def __str__(self) -> str:
        return f"Miner(uid={self.uid}, hotkey={self.hotkey})"


class MinerManager:

    def __init__(self, database_manager: DatabaseManager, metagraph: bt.Metagraph):
        self.database_manager: DatabaseManager = database_manager
        self.metagraph: bt.Metagraph = metagraph
        self.timer: Timer = Timer(timeout=TIMER_COUNTDOWN, run=self.start_task, run_on_start=True)

    def start_task(self) -> None:
        metagraph_miners: set[Miner] = self._get_metagraph_miners()
        self._run(metagraph_miners)

    def _get_active_miners_from_db(self) -> set[Miner]:
        """Return all miners from the active_miners table"""
        with self.database_manager.lock:
            results = self.database_manager.query("SELECT hotkey, uid FROM active_miners")
        if results is None:
            return set()
        return {Miner(hotkey=hotkey, uid=uid) for (hotkey, uid) in results}  # Format query results

    def _get_metagraph_miners(self) -> set[Miner]:
        """Get a list of all miners in the metagraph. Note that this will also include validators, but that's okay"""
        return set([Miner(hotkey=hotkey, uid=index) for index, hotkey in enumerate(self.metagraph.hotkeys)])

    # Pass metagraph miners in as an arg so this can be unit tested
    def _run(self, metagraph_miners: set[Miner]):
        """Clean dereg'd miner data out of database"""
        self._prune_execution_metrics()
        current_thread = threading.current_thread().name
        bt.logging.info(f"| {current_thread} | 🚀 Starting miner management")

        # Build sets
        tracked_miners = self._get_active_miners_from_db()
        bt.logging.info(
            f"| {current_thread} | 🛠️  Managing active miners. Found "
            f"{len(tracked_miners)} tracked hotkeys and {len(metagraph_miners)} metagraph hotkeys"
        )

        # Check for db results
        if len(tracked_miners) == 0:
            bt.logging.info(f"| {current_thread} | ⚠️  Found no hotkeys in the database")
            self._track_new_miners(metagraph_miners, tracked_miners)
            return

        # Get deregistered miners
        deregistered_miners = self._get_deregistered_miners(metagraph_miners, tracked_miners)

        # If we have recently deregistered miners
        if len(deregistered_miners) > 0:

            # Update verified miners. Locking is handled by VerifiedMiners class.

            bt.logging.info(
                f"| {current_thread} | 🚨 Found {len(deregistered_miners)} deregistered hotkeys. "
                f"Cleaning out their data"
            )

            # For all deregistered miners, clear out their data
            tuples = [(x.hotkey,) for x in deregistered_miners]
            with self.database_manager.lock:
                self.database_manager.query_and_commit_many("DELETE FROM last_circuit WHERE miner_hotkey = ?", tuples)
                self.database_manager.query_and_commit_many("DELETE FROM active_miners WHERE hotkey = ?", tuples)
                self.database_manager.query_and_commit_many(
                    "DELETE FROM execution_metrics WHERE miner_hotkey = ?", tuples)

        # Track newly reg'd miners
        self._track_new_miners(metagraph_miners, tracked_miners)

        bt.logging.info(f"| {current_thread} | 🌅 Miner management task complete.")

    def _prune_execution_metrics(self) -> None:
        """Drop execution_metrics rows sent more than 90 days ago."""
        cutoff = (timestamp() - timedelta(days=EXECUTION_METRICS_TTL_DAYS)).strftime(
            TIMESTAMP_FORMAT
        )
        with self.database_manager.lock:
            count_row = self.database_manager.query_one_with_values(
                "SELECT COUNT(*) FROM execution_metrics WHERE time_sent < ?",
                (cutoff,),
            )
            count = int(count_row[0]) if count_row else 0
            if count == 0:
                return
            self.database_manager.query_and_commit_with_values(
                "DELETE FROM execution_metrics WHERE time_sent < ?",
                (cutoff,),
            )
        bt.logging.info(
            f"| {threading.current_thread().name} | "
            f"Pruned {count} execution_metrics rows older than {cutoff}"
        )

    def _track_new_miners(self, metagraph_miners: set[Miner], db_miners: set[Miner]) -> None:
        """Track newly registered miners"""
        current_thread = threading.current_thread().name

        now = timestamp()
        query = """
            INSERT OR IGNORE INTO active_miners (hotkey, uid, timestamp) VALUES(?, ?, ?)
        """
        new_miners = self._get_new_miners(metagraph_miners, db_miners)
        bt.logging.info(f"| {current_thread} | 👀 Tracking {len(new_miners)} new hotkeys")
        tuples = [(x.hotkey, x.uid, now) for x in new_miners]  # Build tuples for insertion
        with self.database_manager.lock:
            self.database_manager.query_and_commit_many(query, tuples)

    def _get_new_miners(self, metagraph_miners: set[Miner], db_miners: set[Miner]) -> List[Miner]:
        """Return the set of new miners"""
        return list(metagraph_miners.difference(db_miners))

    def _get_deregistered_miners(self, metagraph_miners: set[Miner], tracked_miners: set[Miner]) -> List[Miner]:
        """Return the set of deregistered miners"""
        return list(tracked_miners.difference(metagraph_miners))
