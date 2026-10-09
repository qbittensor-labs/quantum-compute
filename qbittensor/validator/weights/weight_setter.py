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

from typing import Any, Dict, List, Optional, Sequence
import bittensor as bt

from qbittensor.utils.services.telemetry import TelemetryService
from qbittensor.validator.weights.epoch import weights_from_epoch


class WeightSetter:
    """Apply a frozen Jobs epoch snapshot to this metagraph."""

    def __init__(
        self,
        metagraph: bt.Metagraph,
        telemetry_service: TelemetryService | None = None,
    ):
        self.metagraph: bt.Metagraph = metagraph
        if telemetry_service is None:
            raise ValueError("telemetry_service must be provided (typed client)")
        self.telemetry_service = telemetry_service

    def weights_from_snapshot(
        self,
        snapshot: Dict[str, Any],
        hotkeys: Optional[Sequence[str]] = None,
        stakes: Optional[Sequence[float]] = None,
    ) -> Optional[List[float]]:
        keys = list(hotkeys) if hotkeys is not None else list(self.metagraph.hotkeys)
        if stakes is None:
            raw = getattr(self.metagraph, "S", None)
            if raw is None:
                stakes_list = [0.0] * len(keys)
            else:
                stakes_list = [float(s) for s in list(raw)[: len(keys)]]
                if len(stakes_list) < len(keys):
                    stakes_list.extend([0.0] * (len(keys) - len(stakes_list)))
        else:
            stakes_list = [float(s) for s in stakes]
        owner = (
            getattr(self.metagraph, "owner_hotkey", None)
            or getattr(getattr(self.metagraph, "raw", None), "owner_hotkey", None)
        )
        if owner is not None:
            owner = str(owner)
        return weights_from_epoch(snapshot, keys, stakes_list, owner_hotkey=owner)
