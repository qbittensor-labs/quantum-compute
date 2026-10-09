# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
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

import copy
import time
import numpy as np
import asyncio
import argparse
import threading
import bittensor as bt

from typing import List, Union
from traceback import print_exception

from qbittensor.base.neuron import BaseNeuron
from qbittensor.base.utils.weight_utils import (
    process_weights_for_netuid,
    convert_weights_and_uids_for_emit,
)
from qbittensor.mock import MockDendrite
from qbittensor.utils.config import add_validator_args

# One sweep, one class-claim, and metagraph sync. Same period for every validator.
_FORWARD_PERIOD_S = 30.0


class BaseValidatorNeuron(BaseNeuron):
    """
    Base class for Bittensor validators. Your validator should inherit from this class.
    """

    neuron_type: str = "ValidatorNeuron"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser):
        super().add_args(parser)
        add_validator_args(cls, parser)

    def __init__(self, config=None):
        super().__init__(config=config)

        # Save a copy of the hotkeys to local memory.
        self.hotkeys = copy.deepcopy(self.metagraph.hotkeys)

        # Dendrite lets us send messages to other nodes (axons) in the network.
        if self.config.mock:
            self.dendrite = MockDendrite(wallet=self.wallet)
        else:
            self.dendrite = bt.Dendrite(wallet=self.wallet)
        bt.logging.info(f"Dendrite: {self.dendrite}")

        # Set up initial scoring weights for validation
        bt.logging.info("Building validation weights.")
        self.scores = np.zeros(self.metagraph.n, dtype=np.float32)

        # Init sync with the network. Updates the metagraph.
        self.sync()

        # Serve axon to enable external connections.
        if not self.config.neuron.axon_off:
            self.serve_axon()
        else:
            bt.logging.warning("axon off, not serving ip to chain.")

        # Instantiate runners
        self.should_exit: bool = False
        self.is_running: bool = False
        self.thread: Union[threading.Thread, None] = None
        self.lock = asyncio.Lock()

    def serve_axon(self):
        """Serve axon to enable external connections."""

        bt.logging.info("serving ip to chain...")
        try:
            self.axon = bt.Axon(wallet=self.wallet, config=self.config)

            try:
                # v11: publish endpoint via ServeAxon intent (no Axon object on chain API).
                self.axon.serve(netuid=self.config.netuid, subtensor=self.subtensor)
                from qbittensor.base.neuron import _endpoint_label

                bt.logging.info(
                    f"Running validator {self.axon} on network: "
                    f"{_endpoint_label(self.subtensor, self.config)} with netuid: {self.config.netuid}"
                )
            except Exception as e:
                bt.logging.warning(
                    f"ServeAxon skipped ({e}). Validators do not need a reachable "
                    "axon; miners still must publish --axon.external_ip."
                )

        except Exception as e:
            bt.logging.error(
                f"Failed to create Axon initialize with exception: {e}"
            )

    def run(self):
        """
        Initiates and manages the main loop for the miner on the Bittensor network. The main loop handles graceful shutdown on keyboard interrupts and logs unforeseen errors.

        This function performs the following primary tasks:
        1. Check for registration on the Bittensor network.
        2. Continuously forwards queries to the miners on the network, rewarding their responses and updating the scores accordingly.
        3. Periodically resynchronizes with the chain; updating the metagraph with the latest network state and setting weights.

        The essence of the validator's operations is in the forward function, which is called every step. The forward function is responsible for querying the network and scoring the responses.

        Note:
            - The function leverages the global configurations set during the initialization of the miner.
            - The miner's axon serves as its interface to the Bittensor network, handling incoming and outgoing requests.

        Raises:
            KeyboardInterrupt: If the miner is stopped by a manual interruption.
            Exception: For unforeseen errors during the miner's operation, which are logged for diagnosis.
        """

        # Check that validator is registered on the network.
        self.sync()

        bt.logging.info(f"Validator starting at block: {self.block}")

        # This loop maintains the validator's operations until intentionally stopped.
        try:
            while not self.should_exit:
                try:
                    bt.logging.info(f"step({self.step}) block({self.block})")
                    started = time.monotonic()

                    # Run single forward.
                    self.forward()

                    # Check if we should exit.
                    if self.should_exit:
                        break

                    # Sync metagraph and potentially set weights.
                    self.sync()

                    remaining = _FORWARD_PERIOD_S - (time.monotonic() - started)
                    slept = 0.0
                    while slept < remaining and not self.should_exit:
                        time.sleep(min(1.0, remaining - slept))
                        slept += 1.0
                    if self.should_exit:
                        break

                    self.step += 1
                except Exception as err:
                    if self.should_exit:
                        break
                    bt.logging.error(f"Error during validation step {self.step}: {str(err)}")
                    bt.logging.debug(
                        str(print_exception(type(err), err, err.__traceback__))
                    )
                    # Continue the loop after transient errors (e.g. handshake timeout)
                    time.sleep(5)

        except KeyboardInterrupt:
            self.should_exit = True
            bt.logging.success("Validator stopped by keyboard interrupt.")
        finally:
            axon = getattr(self, "axon", None)
            if axon is not None:
                try:
                    axon.stop()
                except Exception:
                    bt.logging.debug("axon stop failed during shutdown")

    def run_in_background_thread(self):
        """
        Starts the validator's operations in a background thread upon entering the context.
        This method facilitates the use of the validator in a 'with' statement.
        """
        if self.is_running or self.should_exit:
            return
        bt.logging.debug("Starting validator in background thread.")
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        self.is_running = True
        bt.logging.debug("Started")

    def stop_run_thread(self):
        """
        Stops the validator's operations that are running in the background thread.
        """
        if self.is_running:
            bt.logging.debug("Stopping validator in background thread.")
            self.should_exit = True
            self.thread.join(5)
            self.is_running = False
            bt.logging.debug("Stopped")

    def __enter__(self):
        self.run_in_background_thread()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Stops the validator's background operations upon exiting the context.
        This method facilitates the use of the validator in a 'with' statement.

        Args:
            exc_type: The type of the exception that caused the context to be exited.
                      None if the context was exited without an exception.
            exc_value: The instance of the exception that caused the context to be exited.
                       None if the context was exited without an exception.
            traceback: A traceback object encoding the stack trace.
                       None if the context was exited without an exception.
        """
        if self.is_running:
            bt.logging.debug("Stopping validator in background thread.")
            self.should_exit = True
            self.thread.join(5)
            self.is_running = False
            bt.logging.debug("Stopped")

    def set_weights(self):
        """
        Sets the validator weights to the metagraph hotkeys based on the scores it has received from the miners. The weights determine the trust and incentive level the validator assigns to miner nodes on the network.
        """

        # Check if self.scores contains any NaN values and log a warning if it does.
        if np.isnan(self.scores).any():
            bt.logging.warning(
                "Scores contain NaN values. This may be due to a lack of responses from miners, or a bug in your reward functions."
            )

        # Calculate the average reward for each uid across non-zero values.
        # Replace any NaN values with 0.
        # Compute the norm of the scores
        norm = np.linalg.norm(self.scores, ord=1, axis=0, keepdims=True)

        # Check if the norm is zero or contains NaN values
        if np.any(norm == 0) or np.isnan(norm).any():
            norm = np.ones_like(norm)  # Avoid division by zero or NaN

        # Compute raw_weights safely
        raw_weights = self.scores / norm

        bt.logging.debug("raw_weights", raw_weights)
        bt.logging.debug("raw_weight_uids", str(self.metagraph.uids.tolist()))
        # Process the raw weights to final_weights via subtensor limitations.
        (
            processed_weight_uids,
            processed_weights,
        ) = process_weights_for_netuid(
            uids=self.metagraph.uids,
            weights=raw_weights,
            netuid=self.config.netuid,
            subtensor=self.subtensor,
            metagraph=self.metagraph,
        )
        bt.logging.debug("processed_weights", processed_weights)
        bt.logging.debug("processed_weight_uids", processed_weight_uids)

        # Convert to uint16 weights and uids.
        (
            uint_uids,
            uint_weights,
        ) = convert_weights_and_uids_for_emit(
            uids=processed_weight_uids, weights=processed_weights
        )
        bt.logging.debug("uint_weights", uint_weights)
        bt.logging.debug("uint_uids", uint_uids)

        # Set the weights on chain via v11 SetWeights intent.
        # Pass float proportions (SDK normalizes / quantizes); version_key is the
        # subnet spec version so we remain compatible with on-chain checks.
        try:
            weight_map = {int(u): float(w) for u, w in zip(uint_uids, uint_weights)}
            intent = bt.SetWeights(
                netuid=self.config.netuid,
                weights=weight_map,
                version_key=self.spec_version,
            )
            result = self.subtensor.execute(
                intent,
                self.wallet,
                wait_for_inclusion=False,
                wait_for_finalization=False,
            )
            if getattr(result, "success", False):
                bt.logging.info("set_weights on chain successfully!")
                # execute() does not wait for inclusion. Stamp last_update
                # locally or the next loop submits again.
                self._mark_local_weights_submitted()
            else:
                err = getattr(result, "error", None)
                msg = getattr(err, "remediation", None) or getattr(result, "message", result)
                bt.logging.error("set_weights failed", msg)
        except Exception as exc:
            bt.logging.error(f"set_weights failed: {exc}", exc_info=True)

    def _mark_local_weights_submitted(self) -> None:
        """Pretend last_update is now so should_set_weights() stays false until epoch_length."""
        try:
            uid = int(self.uid)
            last_update = getattr(self.metagraph, "last_update", None)
            if last_update is None:
                return
            last_update[uid] = int(self.block)
        except Exception as exc:
            bt.logging.debug(f"Could not stamp local last_update after set_weights: {exc}")

    def resync_metagraph(self):
        """Resyncs the metagraph and updates the hotkeys and moving averages based on the new metagraph."""
        bt.logging.info("resync_metagraph()")

        # Snapshot only the fields we need — MetagraphAdapter holds a live Subtensor
        # client that is not deepcopy/pickle-safe under SDK v11.
        previous_axons = list(self.metagraph.axons)
        previous_hotkeys = list(self.metagraph.hotkeys)

        # Sync the metagraph.
        self.metagraph.sync(subtensor=self.subtensor)

        # Check if the metagraph axon info has changed.
        if previous_axons == list(self.metagraph.axons):
            return

        bt.logging.info(
            "Metagraph updated, re-syncing hotkeys, dendrite pool and moving averages"
        )
        # Zero out all hotkeys that have been replaced within overlapping range.
        overlap = min(len(previous_hotkeys), len(self.metagraph.hotkeys))
        for uid in range(overlap):
            if previous_hotkeys[uid] != self.metagraph.hotkeys[uid]:
                self.scores[uid] = 0

        # Resize scores to match current metagraph size (handle growth and shrink).
        if len(self.scores) != int(self.metagraph.n):
            new_scores = np.zeros((self.metagraph.n), dtype=self.scores.dtype)
            copy_len = min(len(self.scores), int(self.metagraph.n))
            new_scores[:copy_len] = self.scores[:copy_len]
            self.scores = new_scores

        # Update the hotkeys.
        self.hotkeys = list(self.metagraph.hotkeys)

    def update_scores(self, rewards: np.ndarray, uids: List[int]):
        """Performs exponential moving average on the scores based on the rewards received from the miners."""

        # Check if rewards contains NaN values.
        if np.isnan(rewards).any():
            bt.logging.warning(f"NaN values detected in rewards: {rewards}")
            # Replace any NaN values in rewards with 0.
            rewards = np.nan_to_num(rewards, nan=0)

        # Ensure rewards is a numpy array.
        rewards = np.asarray(rewards)

        # Check if `uids` is already a numpy array and copy it to avoid the warning.
        if isinstance(uids, np.ndarray):
            uids_array = uids.copy()
        else:
            uids_array = np.array(uids)

        # Handle edge case: If either rewards or uids_array is empty.
        if rewards.size == 0 or uids_array.size == 0:
            bt.logging.info(f"rewards: {rewards}, uids_array: {uids_array}")
            bt.logging.warning(
                "Either rewards or uids_array is empty. No updates will be performed."
            )
            return

        # Check if sizes of rewards and uids_array match.
        if rewards.size != uids_array.size:
            raise ValueError(
                f"Shape mismatch: rewards array of shape {rewards.shape} "
                f"cannot be broadcast to uids array of shape {uids_array.shape}"
            )

        # Compute forward pass rewards, assumes uids are mutually exclusive.
        # shape: [ metagraph.n ]
        scattered_rewards: np.ndarray = np.zeros_like(self.scores)
        scattered_rewards[uids_array] = rewards
        bt.logging.debug(f"Scattered rewards: {rewards}")

        # Update scores with rewards produced by this step.
        # shape: [ metagraph.n ]
        alpha: float = self.config.neuron.moving_average_alpha
        self.scores: np.ndarray = (
            alpha * scattered_rewards + (1 - alpha) * self.scores
        )
        bt.logging.debug(f"Updated moving avg scores: {self.scores}")

    def save_state(self):
        """Saves the state of the validator to a file."""
        bt.logging.info("Saving validator state.")

        # Save the state of the validator to file.
        np.savez(
            self.config.neuron.full_path + "/state.npz",
            step=self.step,
            scores=self.scores,
            hotkeys=self.hotkeys,
        )

    def load_state(self):
        """Loads the state of the validator from a file."""
        bt.logging.info("Loading validator state.")

        # Load the state of the validator from file.
        state = np.load(self.config.neuron.full_path + "/state.npz")
        self.step = state["step"]
        self.scores = state["scores"]
        self.hotkeys = state["hotkeys"]
