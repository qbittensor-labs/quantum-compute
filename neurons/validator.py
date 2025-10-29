import threading
import time
from typing import Any, List
import bittensor as bt
from time import sleep

from pkg.database.database_manager import DatabaseManager
from qbittensor.validator.heartbeat import Heartbeat
from qbittensor.validator.miner_manager.MinerManager import MinerManager
from qbittensor.utils.request.RequestManager import RequestManager
from qbittensor.validator.miner_manager.NextMiner import BasicMiner, NextMiner
from qbittensor.validator.vali_table_initializer import ValidatorTableInitializer
from qbittensor.base.validator import BaseValidatorNeuron
from qbittensor.validator.reward.score import Scorer
from qbittensor.validator.synapse.SynapseManager import SynapseManager
from qbittensor.validator.weights.WeightSetter import WeightSetter


class Validator(BaseValidatorNeuron):

    def __init__(self, config=None):
        super(Validator, self).__init__(config=config)

        # Database
        my_hotkey = self.wallet.hotkey.ss58_address
        database_manager = DatabaseManager(f"validator_{my_hotkey}")
        table_initializer = ValidatorTableInitializer(database_manager)
        table_initializer.create_tables()

        # Request manager
        request_manager = RequestManager(self.wallet.hotkey, node_type="validator", network=self.subtensor.network)

        # Helpers
        self.synapse_manager = SynapseManager(database_manager, request_manager)
        self.scorer = Scorer(database_manager, self.metagraph, request_manager)
        self.next_miner = NextMiner(self.metagraph)

        # Miner management
        self.miner_manager = MinerManager(database_manager, self.metagraph)

        # Setting weights
        self.weight_setter = WeightSetter(
            self.metagraph,
            self.wallet,
            request_manager,
            database_manager,
            self.subtensor.network
        )
        
        # Heartbeat
        self.heartbeat = Heartbeat(request_manager)

    def forward(self):
        """Forward function for the validator"""
        current_thread = threading.current_thread().name
        bt.logging.info(f"| {current_thread} | ⏩ Running forward pass")

        synapse, original_compute_request, next_miner = None, None, None

        while synapse is None or next_miner is None or original_compute_request is None:
            try:
                next_miner: BasicMiner | None = self.next_miner.get_next_miner()
            except IndexError:
                bt.logging.trace(f"| {current_thread} | ❌  Forward pass failed to find the next miner, returning")
                return
            bt.logging.info(f"| {current_thread} | 🔗  Next miner '{next_miner}'")

            # Get synapse and original compute request
            synapse, original_compute_request = self.synapse_manager.get_synapse(next_miner)
            if synapse is None:
                sleep(1)

        # Query the metagraph
        response: List[Any] = self.dendrite.query(
            axons=[next_miner.axon],
            synapse=synapse,
            deserialize=True,
            timeout=10
        )
        if response is None:
            bt.logging.info(f"| {current_thread} | ❗ No responses from miner '{next_miner}'.")
            return

        self.scorer.process_miner_responses(response, next_miner, original_compute_request)

    def run(self):

        # Used to track metagraph syncs
        step = 1

        # Main loop
        try:
            while True:
                
                # Check timers
                self.heartbeat.timer.check_timer()
                self.miner_manager.timer.check_timer()
                self.weight_setter.check_timer()

                # Call to forward()
                self.forward()
                
                # Sleep and maintain step
                time.sleep(5)
                step += 1

                # Resync the metagraph every so often
                if step > 20:
                    step = 1
                    self.resync_metagraph()

        finally:
            bt.logging.info("Stopping the validator")

# The main function parses the configuration and runs the validator.
if __name__ == "__main__":
    Validator().run()
