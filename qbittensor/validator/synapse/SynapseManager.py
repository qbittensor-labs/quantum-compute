from typing import Tuple
import requests
import bittensor as bt

from qbittensor.protocol import COLLECT_SYNAPSE_ID, CircuitSynapse
from pkg.database.database_manager import DatabaseManager
from qbittensor.utils.telemetry.TelemetryService import TelemetryService
from qbittensor.validator.compute_request.ComputeRequest import ComputeRequest
from qbittensor.utils.request.RequestManager import RequestManager
from qbittensor.validator.miner_manager.NextMiner import BasicMiner

START_OF_TIME = "0000-00-00 00:00:00"


class SynapseManager:

    def __init__(self, database_manager: DatabaseManager, request_manager: RequestManager):
        self.database_manager = database_manager
        self.request_manager = request_manager
        self.telemetry_service = TelemetryService(request_manager)
        
    def get_synapse(self, next_miner: BasicMiner) -> Tuple[CircuitSynapse | None, ComputeRequest | None]:
        """Build a synapse from the requests queue data"""

        # Hit job server for compute request
        next_compute_request = self._get_execution(next_miner.hotkey)

        # If we find no data
        if next_compute_request is None:
            return None, None
        
        bt.logging.trace(f"🔍 Fetched next compute request: {next_compute_request.execution_id}")
        self.telemetry_service.vali_record_execution_from_jobs_api(
            execution_id=next_compute_request.execution_id,
            miner_uid=next_miner.uid,
            miner_hotkey=next_miner.hotkey
        )
        
        # Build the synapse object
        last_circuit = self._get_last_circuit_timestamp(next_miner.hotkey)
        synapse = CircuitSynapse(execution_id=next_compute_request.execution_id, shots=next_compute_request.shots, configuration_data=next_compute_request.configuration_data, input_data_url=next_compute_request.input_data_url, last_circuit=last_circuit)

        # Return
        return synapse, next_compute_request
    
    def _get_execution(self, miner_hotkey: str) -> ComputeRequest | None:
        """Hit the job server and get a compute request"""

        endpoint = "executions"
        params = {"miner_hotkey": miner_hotkey}
        response: requests.Response = self.request_manager.get(endpoint, params=params)

        # Handle no-data codes
        if response.status_code == 401 or response.status_code == 404:
            bt.logging.trace(f"🚫 This node is not an onboarded miner")
            return None

        if response.status_code == 204:
            bt.logging.trace(f"📭  No new execution available from job server. Sending a collect-only request")
            return ComputeRequest(execution_id=COLLECT_SYNAPSE_ID, shots=0, configuration_data={}, input_data_url="")  # Return empty object to indicate no job found. Do this so we can collect all finished jobs from miner in the synapse response.

        if response.status_code == 200:
            try:
                data = response.json()
                return ComputeRequest.from_api_response(data)
            except ValueError:
                bt.logging.error(f"❌ Failed to parse JSON /compute response from job server")
                return None
        else:
            bt.logging.error(f"❌ job server returned unexpected status code: {response.status_code}")
            return None
    
    def _get_last_circuit_timestamp(self, miner_hotkey: str) -> str:
        """Query the dtabase for the last circuit from this miner"""
        query = """
            SELECT timestamp
            FROM last_circuit
            WHERE miner_hotkey=?
        """
        values = (miner_hotkey,)
        with self.database_manager.lock:
            result = self.database_manager.query_one_with_values(query, values)
        if result is None:
            return START_OF_TIME
        return result[0]
