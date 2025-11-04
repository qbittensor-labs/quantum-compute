import threading
import time
import typing
import bittensor as bt
from typing import List, Tuple
import argparse
from types import SimpleNamespace
import requests

# Bittensor Miner Template:
from pkg.database.database_manager import DatabaseManager
from qbittensor.miner.miner_table_initializer import MinerTableInitializer

# import base miner class which takes care of most of the boilerplate
from qbittensor.base.miner import BaseMinerNeuron
from qbittensor.protocol import COLLECT_SYNAPSE_ID, CircuitSynapse, ExecutionData
from qbittensor.miner.runtime.registry import JobRegistry
from qbittensor.utils.request.RequestManager import RequestManager
from qbittensor.utils.telemetry.TelemetryService import TelemetryService
from qbittensor.utils.timestamping import timestamp_str

COMPLETED_CIRCUIT_TTL = 14 # Keep circuits around for 2 weeks


class Miner(BaseMinerNeuron):

    def __init__(self, config=None):
        super(Miner, self).__init__(config=config)
        my_hotkey = self.wallet.hotkey.ss58_address
        self.database_manager = DatabaseManager(f"miner_{my_hotkey}")
        table_initializer = MinerTableInitializer(self.database_manager)
        table_initializer.create_tables()
        request_manager = RequestManager(self.wallet.hotkey, node_type="miner", network=self.subtensor.network)
        self.telemetry_service = TelemetryService(request_manager)
        self.jobs = JobRegistry(self.database_manager, self.wallet.hotkey)
        try:
            setattr(self.jobs, "_telemetry_service", self.telemetry_service)
            setattr(self.jobs, "_miner_uid", self.uid)
        except Exception:
            pass

    def forward(self, synapse: CircuitSynapse) -> CircuitSynapse:
        """Forward for the miner. Parse data, start circuit, update database, send response"""
        self.telemetry_service.miner_record_execution_received(synapse.execution_id, self.uid, self.wallet.hotkey.ss58_address)
        
        current_thread = threading.current_thread().name

        # Get the validator hotkey. If undefined, return the synapse with no ExecutionData
        validator_hotkey = self._get_validator_hotkey(synapse)
        if validator_hotkey is None:
            bt.logging.trace(f"| {current_thread} | ❗ Failed to extract validator hotkey")
            return synapse
        
        bt.logging.trace(f"| {current_thread} | 🚚 Received synapse from validator '{validator_hotkey}'")

        # Update the synapse by reference, adding all completed circuits from the database
        self._update_synapse_with_finished_executions(synapse)

        # Maintain the database        
        self._drop_old_circuit_data()
        
        if synapse.execution_id == COLLECT_SYNAPSE_ID:
            bt.logging.trace(f"| {current_thread} | 📬 Received collect-only request from validator '{validator_hotkey}'")
            return synapse

        if self._rate_limit():
            bt.logging.trace(f"| {current_thread} | 🚧 Rate limiting this request")
            synapse.rate_limited = True
        
        elif self._job_is_new(synapse.execution_id):
            try:
                response = requests.get(synapse.input_data_url, timeout=5)
                response.raise_for_status()
                self.jobs.submit(
                    execution_id=synapse.execution_id,
                    input_data_url=synapse.input_data_url,
                    validator_hotkey=validator_hotkey,
                    shots=synapse.shots,
                )
            except Exception as e:
                bt.logging.debug(f"❌ Submit failed for execution {synapse.execution_id}: {e}")
                
        return synapse
    
    def _rate_limit(self) -> bool:
        """Returns whether or not this request should be ignored due to rate limiting"""
        # TODO Developer. When implementing your miner, add your own rate limiting logic here
        return False
    
    def _update_synapse_with_finished_executions(self, synapse: CircuitSynapse) -> None:
        """Add completed circuits to the synapse"""
        current_thread = threading.current_thread().name

        # Get completed jobs from database
        last_update = synapse.last_circuit
        finished_executions, last_circuit = self._get_finished_executions(last_update)
        bt.logging.trace(f"| {current_thread} | 📋 Found {len(finished_executions)} finished jobs")

        # Add completed jobs to synapse
        synapse.finished_executions.extend(finished_executions)
        synapse.last_circuit = last_circuit # Update the synapse with the timestamp of the most recently returned circuit
        synapse.success = True # Lets the validator know that this request was serviced successfully

    def _get_finished_executions(self, last_update: str) -> Tuple[List[ExecutionData], str]:
        """Get a list of ExecutionData objects from the database"""

        # Query database for completed circuits
        if not last_update:
            last_update = "1970-01-01 00:00:00"
        query="""
            SELECT execution_id, COALESCE(shots, 0) as shots, upload_data_id, provider_job_id, status, errorMessage, timestamp
            FROM executions
            WHERE timestamp > ? AND status != 'Running'
        """
        values = (last_update,)
        with self.database_manager.lock:
            results = self.database_manager.query_with_values(query, values)

        # Build list of ExecutionData objects from db query results
        finished_executions = [
            ExecutionData(
                execution_id=execution_id,
                shots=shots,
                upload_data_id=upload_data_id,
                execution_data={"provider_job_id": provider_job_id},
                status=status,
                errorMessage=errorMessage,
            )
            for (execution_id, shots, upload_data_id, provider_job_id, status, errorMessage, _) in results
        ]

        # Build list of timestamps from db query results
        timestamps = [timestamp for (_, _, _, _, _, _, timestamp) in results]

        # Get the most recent timestamp. If no data came back from query, default this to the same timestamp the validator sent.
        most_recent_timestamp = last_update
        if len(timestamps) > 0:
            most_recent_timestamp = max(timestamps)

        # Return a tuple
        return finished_executions, most_recent_timestamp

    def _drop_old_circuit_data(self) -> None:
        """Drop any data from executions table older than n days"""
        query = f"""
            DELETE FROM executions
            WHERE timestamp < date('now', '-{COMPLETED_CIRCUIT_TTL} days')
        """
        with self.database_manager.lock:
            self.database_manager.query_and_commit(query)

    def _job_is_new(self, execution_id: str) -> bool:
        """Check if this request id has been seen yet"""
        try:
            if hasattr(self, "jobs") and self.jobs.is_tracking(execution_id):
                return False
        except Exception:
            pass
        table = "executions"
        conditions = "execution_id=?"
        values = (execution_id,)
        with self.database_manager.lock:
            return not self.database_manager.row_exists(table, conditions, values)
        
    def _execute_circuit(self, synapse: CircuitSynapse) -> None:
        """Execute the circuit in a separate thread"""
        threading.Thread(target=self._start_circuit_worker, name="⛏️ Circuit Worker ⛏️", args=(synapse,)).start()

    def _start_circuit_worker(self, synapse: CircuitSynapse) -> None:
        """Implement circuit running"""
        """
        NOTE To developers
        The timestamp field in the executions table must be lexicographically sortable. We recomment you use the following code to generate it.

        today = datetime.now(timezone.utc)
        timestamp = today.strftime("%Y-%m-%d %H:%M:%S")

        When a circuit completes, store it's data in the executions table, with the timestamp field created as above.
        """
        current_thread = threading.current_thread().name
        bt.logging.info(f"| {current_thread} | 🚀 Starting circuit worker!")

        # TODO Developer.Implement this. Run circuit, store results in database.

    def _get_validator_hotkey(self, synapse: CircuitSynapse) -> str | None:
        """Return the validator hotkey for this synapse"""
        if not synapse.dendrite:
            return None
        return synapse.dendrite.hotkey

    def blacklist(self, synapse: CircuitSynapse) -> typing.Tuple[bool, str]:
        """Blacklist maintains list of untrusted nodes"""

        # Check if synapse hotkey is in the metagraph
        if not synapse.dendrite or synapse.dendrite.hotkey not in self.metagraph.hotkeys:
            validator_hotkey = synapse.dendrite.hotkey if synapse.dendrite else "UNKNOWN"
            bt.logging.info(f"❗Blacklisted unknown hotkey: {validator_hotkey}")
            return True, f"❗Hotkey {validator_hotkey} was not found from metagraph.hotkeys",

        stake, uid = self.get_validator_stake_and_uid(synapse.dendrite.hotkey)

        # Check if validator has sufficient stake
        validator_min_stake = 0.0
        if stake < validator_min_stake:
            bt.logging.info(f"❗Blacklisted validator {synapse.dendrite.hotkey} with insufficient stake: {stake}")
            return True, f"❗Hotkey {synapse.dendrite.hotkey} has insufficient stake: {stake}",

        # Valid hotkey
        bt.logging.info(f"✅ Accepted hotkey: {synapse.dendrite.hotkey} (UID: {uid} - Stake: {stake})")
        return False, f"✅ Accepted hotkey: {synapse.dendrite.hotkey}"

    def priority(self, synapse: CircuitSynapse) -> float:
        """Priority function determines order in which requests are handled"""
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning(
                "Received a request without a dendrite or hotkey."
            )
            return 0.0

        bt.logging.debug(f"🧮 Calculating priority for synapse from {synapse.dendrite.hotkey}")
        stake, uid = self.get_validator_stake_and_uid(synapse.dendrite.hotkey)
        bt.logging.debug(f"🏆 Prioritized: {synapse.dendrite.hotkey} (UID: {uid} - Stake: {stake})")
        return stake

    # HELPER
    def get_validator_stake_and_uid(self, hotkey):
        uid = self.metagraph.hotkeys.index(hotkey)  # get uid
        return float(self.metagraph.S[uid]), uid  # return validator stake


# This is the main function, which runs the miner.
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    Miner.add_args(parser)
    config = bt.config(parser)

     # Set blacklist config to avoid security warnings
    if not hasattr(config, 'blacklist') or config.blacklist is None:
        config.blacklist = bt.config()
        if config.blacklist is None:
            config.blacklist = SimpleNamespace()
    config.blacklist.allow_non_registered = False
    config.blacklist.force_validator_permit = True
    
    with Miner() as miner:
        miner.jobs.start()
        while True:
            bt.logging.info(f"Miner running... {timestamp_str()}")
            time.sleep(5)
