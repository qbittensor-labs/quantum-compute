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

from typing import List, Tuple
import bittensor as bt

from qbittensor.protocol import COLLECT_SYNAPSE_ID, CircuitSynapse
from qbittensor.database.database_manager import DatabaseManager
from qbittensor.utils.services.telemetry import TelemetryService
from qbittensor.utils.services.job import JobClient
from qbittensor.validator.compute_request.compute_request import ComputeRequest
from qbittensor.validator.miner_manager.next_miner import BasicMiner

from qbittensor.constants import START_OF_TIME


class SynapseManager:

    def __init__(
        self,
        database_manager: DatabaseManager,
        telemetry_service: TelemetryService | None = None,
        job_client: JobClient | None = None,
    ):
        self.database_manager = database_manager
        self.job_client = job_client
        if telemetry_service is None:
            raise ValueError("telemetry_service must be provided (typed client)")
        self.telemetry_service = telemetry_service

    def get_synapse(self, next_miner: BasicMiner) -> Tuple[CircuitSynapse | None, ComputeRequest | None]:
        next_compute_request = self._get_execution(next_miner.hotkey)
        if next_compute_request is None:
            return None, None

        bt.logging.trace(f"🔍 Fetched next compute request: {next_compute_request.execution_id}")
        self.telemetry_service.vali_record_execution_from_jobs_api(
            execution_id=next_compute_request.execution_id,
            miner_hotkey=next_miner.hotkey,
        )

        return self.synapse_from_compute(next_compute_request, next_miner)

    def collect_only_synapse(self, next_miner: BasicMiner) -> Tuple[CircuitSynapse, ComputeRequest]:
        """Build a collect-only CircuitSynapse (no new work)."""
        compute = ComputeRequest(
            execution_id=COLLECT_SYNAPSE_ID,
            shots=0,
            configuration_data={},
            input_data_url="",
        )
        synapse, _ = self.synapse_from_compute(compute, next_miner)
        return synapse, compute

    def get_synapse_for_classes(
        self,
        classes: List[str],
        actor_id: str | None = None,
        miner: BasicMiner | None = None,
    ) -> Tuple[CircuitSynapse | None, ComputeRequest | None]:
        """Claim a PUBLIC execution matching backend class short_codes."""
        if self.job_client is None:
            raise ValueError("job_client must be provided to SynapseManager")
        data = self.job_client.get_execution_for_classes(classes, actor_id=actor_id)
        if data is None:
            return None, None
        compute = self._compute_from_payload(data)
        if miner is None:
            synapse = CircuitSynapse(
                execution_id=compute.execution_id,
                shots=compute.shots,
                configuration_data=compute.configuration_data,
                backend_class_id=compute.backend_class_id,
                input_data_url=compute.input_data_url,
                last_circuit=START_OF_TIME,
            )
            return synapse, compute
        self.telemetry_service.vali_record_execution_from_jobs_api(
            execution_id=compute.execution_id,
            miner_hotkey=miner.hotkey,
        )
        return self.synapse_from_compute(compute, miner)

    def synapse_from_compute(
        self,
        compute: ComputeRequest,
        miner: BasicMiner,
    ) -> Tuple[CircuitSynapse, ComputeRequest]:
        last_circuit = self._get_last_circuit_timestamp(miner.hotkey)
        synapse = CircuitSynapse(
            execution_id=compute.execution_id,
            shots=compute.shots,
            configuration_data=compute.configuration_data,
            backend_class_id=compute.backend_class_id,
            input_data_url=compute.input_data_url,
            last_circuit=last_circuit,
        )
        return synapse, compute

    def _compute_from_payload(self, data: dict) -> ComputeRequest:
        if data.get("execution_id") == COLLECT_SYNAPSE_ID:
            return ComputeRequest(
                execution_id=COLLECT_SYNAPSE_ID,
                shots=0,
                configuration_data={},
                input_data_url="",
            )
        try:
            return ComputeRequest.from_api_response(data)
        except Exception:
            cfg = data.get("configuration_data") or {}
            if not isinstance(cfg, dict):
                cfg = {}
            raw_shots = cfg.get("shots")
            try:
                shots = int(raw_shots) if raw_shots is not None else 0
            except (TypeError, ValueError):
                shots = 0
            return ComputeRequest(
                execution_id=data.get("execution_id", ""),
                input_data_url=data.get("input_data_url", ""),
                shots=shots,
                configuration_data=cfg,
                backend_class_id=data.get("backend_class_id"),
            )

    def _get_execution(self, miner_hotkey: str) -> ComputeRequest | None:
        """Hit the job server and get a compute request using JobClient."""
        if self.job_client is None:
            raise ValueError("job_client must be provided to SynapseManager")
        data = self.job_client.get_execution_for_miner(miner_hotkey)
        if data is None:
            return None
        return self._compute_from_payload(data)

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
