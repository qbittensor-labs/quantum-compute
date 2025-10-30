import threading
from typing import Any, Dict, List
import bittensor as bt

from pkg.database.database_manager import DatabaseManager
from qbittensor.protocol import COLLECT_SYNAPSE_ID, CircuitSynapse, ExecutionData
from qbittensor.utils.telemetry.TelemetryService import TelemetryService
from qbittensor.utils.timestamping import timestamp_str
from qbittensor.validator.compute_request.ComputeRequest import ComputeRequest
from qbittensor.utils.request.RequestManager import RequestManager
from qbittensor.validator.miner_manager.NextMiner import BasicMiner
from qbittensor.validator.utils.execution_status import ExecutionStatus
from qbittensor.validator.utils.execution_metrics import ExecutionMetrics


class Scorer:

    def __init__(self, database_manager: DatabaseManager, metagraph: bt.Metagraph, request_manager: RequestManager):
        self.database_manager: DatabaseManager = database_manager
        self.metagraph: bt.Metagraph = metagraph
        self.request_manager: RequestManager = request_manager
        self._metrics: ExecutionMetrics = ExecutionMetrics(database_manager)
        self.telemetry_service = TelemetryService(request_manager)

    def process_miner_responses(self, responses: List[CircuitSynapse], next_miner: BasicMiner, original_compute_request_data: ComputeRequest):
        """Process responses from every miner"""
        current_thread: str = threading.current_thread().name

        for synapse in responses:
            self.telemetry_service.vali_record_synapse_response(
                execution_id=synapse.execution_id,
                miner_uid=next_miner.uid,
                miner_hotkey=next_miner.hotkey,
                error_message=synapse.error_message,
                success=synapse.success,
                rate_limited=synapse.rate_limited
            )
            try:
                # Handle miner disconnected. Currently using `success` field in the synapse. This will cause a retry with the original compute request
                if not synapse.success:
                    if synapse.error_message:
                        bt.logging.info(f"| {current_thread} | ❗ Synapse error message from miner '{next_miner.hotkey}': {synapse.error_message}")
                        msg = synapse.error_message
                    else:
                        msg = "Miner did not respond"
                    self._patch_job_rejected(synapse.execution_id, msg)
                    bt.logging.info(f"| {current_thread} | ❗ Synapse success field is false from miner '{next_miner.hotkey}'.")
                    continue

                # If we got rate limited, push this circuit back on the queue. This will cause a retry with the original compute request
                if synapse.rate_limited:
                    self._patch_job_rejected(synapse.execution_id, "Miner is rate limiting")
                    bt.logging.trace(f"| {current_thread} | 🚦 Handling rate limited request {original_compute_request_data}.")
    
                # The miner successfully picked up the circuit
                else:
                    # Patch the new status
                    if original_compute_request_data.execution_id != COLLECT_SYNAPSE_ID:
                        self._patch_execution_status(original_compute_request_data.execution_id, synapse.execution_status)
                        # Record the execution_cost
                        self._record_execution(next_miner.hotkey, original_compute_request_data.execution_id, original_compute_request_data.shots)

                # If no finished executions, we don't want to update the last circuit table
                if synapse.finished_executions is None or len(synapse.finished_executions) == 0:
                    bt.logging.trace(f"| {current_thread} | ⚠️  No finished executions in this response")
                    continue

                num_pending = sum(1 for exec in synapse.finished_executions if exec.status == ExecutionStatus.PENDING)
                num_queued = sum(1 for exec in synapse.finished_executions if exec.status == ExecutionStatus.QUEUED)
                num_running = sum(1 for exec in synapse.finished_executions if exec.status == ExecutionStatus.RUNNING)
                num_failed = sum(1 for exec in synapse.finished_executions if exec.status == ExecutionStatus.FAILED)
                num_completed = sum(1 for exec in synapse.finished_executions if exec.status == ExecutionStatus.COMPLETED)

                bt.logging.trace(f"| {current_thread} | 📊  Finished executions detail\n----------------------------\n⭐  Number of completed executions: {num_completed}\n🚩  Number of failed executions: {num_failed}\n▶️  Number of running executions: {num_running}\n⏳   Number of queued executions: {num_queued}\n⏸️   Number of pending executions: {num_pending}\n----------------------------")

                self._metrics.upsert_last_circuit(next_miner.hotkey, synapse.last_circuit)

                for execution in synapse.finished_executions:
                    try:
                        self.telemetry_service.vali_record_execution_from_miner(
                            execution_id=execution.execution_id,
                            status=execution.status,
                            miner_uid=next_miner.uid,
                            miner_hotkey=next_miner.hotkey,
                        )
                        if execution.status == ExecutionStatus.COMPLETED:
                            self._record_time_received(next_miner.hotkey, execution.execution_id)  # Update local database
                            self._patch_job_complete(execution)  # Send to job server
                            bt.logging.trace(f"| {current_thread} | ✅  Miner reported successfuly completion for execution_id {execution.execution_id}")
                        elif execution.status == ExecutionStatus.FAILED:
                            error_msg = execution.errorMessage if execution.errorMessage else "Miner reported failure"
                            self._patch_job_rejected(execution.execution_id, error_msg)  # Send to job server
                            bt.logging.trace(f"| {current_thread} | ❌  Miner reported failure for execution_id {execution.execution_id} with message: {error_msg}")

                    except Exception as e:
                        bt.logging.error(f"| {current_thread} | ❌ Error processing finished execution execution_id={execution.execution_id} err={e}")

            except Exception as e:
                bt.logging.error(f"| {current_thread} | ❌ Error handling miner response: {e}")

    def _patch_job_rejected(self, execution_id: str, message: str) -> None:
        """Send the request back to the job server because retries exceeded"""
        body: Dict[str, str] = {
            "status": ExecutionStatus.FAILED,
            "message": message
        }
        self._patch(execution_id, body)
    
    def _patch_job_complete(self, execution: ExecutionData) -> None:
        """Submit the execution to the job server"""
        if not execution.upload_data_id:
            bt.logging.debug(f"❗ Cannot patch job complete for execution {execution.execution_id} because upload_data_id is missing")
            return
        body: Dict[str, Any] = {
            "status": ExecutionStatus.COMPLETED,
            "upload_id": execution.upload_data_id,
            "execution_data": execution.execution_data
        }
        self._patch(execution.execution_id, body)
        
    def _patch_execution_status(self, execution_id: str, status: ExecutionStatus) -> None:
        """Send the request back to the job server with the new status"""
        body: Dict[str, Any] = {
            "status": status,
        }
        self._patch(execution_id, body)

    def _patch(self, execution_id: str, body: Dict) -> None:
        """Helper function to patch the job server"""
        if execution_id == COLLECT_SYNAPSE_ID:
            return
        bt.logging.debug(f"📌 Patching job server for execution_id {execution_id} with body {body}")
        endpoint: str = f"executions/{execution_id}"
        try:
            self.request_manager.patch(endpoint, body)
        except Exception as e:
            bt.logging.trace(f"❗ Failed to patch job server at endpoint {endpoint} with body {body}: {e}")

    def _update_last_circuit_table(self, synapse: CircuitSynapse, miner_hotkey: str) -> None:
        """Extract the timestamp of the most recent circuit, store it"""

        try:
            last_update_timestamp = synapse.last_circuit
            query = """
                INSERT OR REPLACE into last_circuit
                (miner_hotkey, timestamp)
                VALUES (?, ?)
            """
            values = (miner_hotkey, last_update_timestamp)
            with self.database_manager.lock:
                self.database_manager.query_and_commit_with_values(query, values)

        # Handle bad data from the miner
        except Exception as e:
            current_thread = threading.current_thread().name
            bt.logging.debug(f"| {current_thread} | ❌ Error processing last_circuit timestamp from miner '{miner_hotkey}': {e}")

    def _record_execution(self, miner_hotkey: str, execution_id: str, shots: int | None = None) -> None:
        self._metrics.insert_job_sent(miner_hotkey, execution_id, shots, timestamp_str())

    def _record_time_received(self, miner_hotkey: str, execution_id: str) -> None:
        self._metrics.update_time_received(miner_hotkey, execution_id, timestamp_str())
