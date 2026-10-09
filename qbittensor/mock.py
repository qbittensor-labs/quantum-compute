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

"""Lightweight mocks for local/unit testing under bittensor SDK v11.

v11 removed MockSubtensor / the old Metagraph sync surface. These stand-ins keep
the ``--mock`` neuron path importable without a live chain. The surface mirrors
v11 only (subnets.metagraph, neurons.uid, .block, hyperparameters, execute).
"""

from __future__ import annotations

import time
import asyncio
import random
from types import SimpleNamespace
from typing import List, Any

import bittensor as bt

from qbittensor import bt_compat  # noqa: F401
from qbittensor.bt_compat import MetagraphAdapter, Synapse


class MockSubtensor:
    """Minimal stand-in for the removed bt.MockSubtensor (v11 surface only)."""

    def __init__(self, netuid: int, n: int = 16, wallet=None, network: str = "mock"):
        self.network = network
        self.endpoint = "mock"
        self.netuid = netuid
        self._n = n
        self._wallet = wallet
        self._hotkeys = []
        self._coldkeys = []
        if wallet is not None:
            self._hotkeys.append(wallet.hotkey.ss58_address)
            self._coldkeys.append(getattr(wallet.coldkey, "ss58_address", "mock-cold"))
        for i in range(1, n + 1):
            self._hotkeys.append(f"miner-hotkey-{i}")
            self._coldkeys.append("mock-coldkey")
        self.block = 0

    @property
    def subnets(self):
        parent = self

        class _Subnets:
            def metagraph(self, netuid: int, **_):
                return parent._build_metagraph(netuid)

        return _Subnets()

    @property
    def neurons(self):
        parent = self

        class _Neurons:
            def uid(self, hotkey_ss58: str, netuid: int):
                try:
                    return parent._hotkeys.index(hotkey_ss58)
                except ValueError:
                    return None

        return _Neurons()

    @property
    def hyperparameters(self):
        class _HP:
            def min_allowed_weights(self, netuid: int = None, **_):
                return 1

            def max_weight_limit(self, netuid: int = None, **_):
                return 1.0

        return _HP()

    def execute(self, intent, wallet, **_):
        return SimpleNamespace(success=True, message="ok", error=None)

    def _build_metagraph(self, netuid: int):
        neurons = []
        for uid, (hk, ck) in enumerate(zip(self._hotkeys, self._coldkeys)):
            neurons.append(
                SimpleNamespace(
                    uid=uid,
                    hotkey=hk,
                    coldkey=ck,
                    validator_permit=(uid == 0),
                    last_update=0,
                    total_stake=SimpleNamespace(
                        amount=100000.0 if uid == 0 else 1000.0,
                        tao=100000.0 if uid == 0 else 1000.0,
                    ),
                    axon="127.0.0.0:8091",
                    emission=SimpleNamespace(amount=0.0),
                )
            )
        mg = SimpleNamespace(
            netuid=netuid,
            neurons=neurons,
            hotkeys=self._hotkeys[:],
            coldkeys=self._coldkeys[:],
            block=self.block,
            num_uids=len(neurons),
        )
        return MetagraphAdapter(mg, netuid=netuid, subtensor=self)


class MockMetagraph(MetagraphAdapter):
    def __init__(self, netuid: int = 1, network: str = "mock", subtensor=None):
        if subtensor is None:
            subtensor = MockSubtensor(netuid=netuid, network=network)
        mg = subtensor.subnets.metagraph(netuid=netuid)
        # mg may already be a MetagraphAdapter
        if isinstance(mg, MetagraphAdapter):
            super().__init__(
                mg.raw if hasattr(mg, "raw") else mg,
                netuid=netuid,
                subtensor=subtensor,
            )
            self.__dict__.update(
                {k: v for k, v in vars(mg).items() if not k.startswith("_") or k in ("_mg",)}
            )
            self._mg = getattr(mg, "_mg", mg)
            self._rebuild()
        else:
            super().__init__(mg, netuid=netuid, subtensor=subtensor)

        for axon in self.axons:
            axon.ip = "127.0.0.0"
            axon.port = 8091

        bt.logging.info(f"Metagraph: {self}")
        bt.logging.info(f"Axons: {self.axons}")


class MockDendrite(bt.Dendrite):
    """
    Replaces a real bittensor network request with a mock request that just returns
    some static response for all axons that are passed and adds some random delay.
    """

    def __init__(self, wallet):
        super().__init__(wallet)

    async def forward(
        self,
        axons: List[Any],
        synapse: Any = None,
        timeout: float = 12,
        deserialize: bool = True,
        run_async: bool = True,
        streaming: bool = False,
    ):
        if streaming:
            raise NotImplementedError("Streaming not implemented yet.")

        if synapse is None:
            synapse = Synapse()

        async def query_all_axons(streaming: bool):
            async def single_axon_response(i, axon):
                start_time = time.time()
                s = synapse.copy() if hasattr(synapse, "copy") else synapse
                process_time = random.random()
                if s.dendrite is None:
                    from qbittensor.bt_compat import TerminalInfo

                    s.dendrite = TerminalInfo()
                if process_time < timeout:
                    s.dendrite.process_time = str(time.time() - start_time)
                    s.dendrite.status_code = 200
                    s.dendrite.status_message = "OK"
                else:
                    s.dendrite.status_code = 408
                    s.dendrite.status_message = "Timeout"
                    s.dendrite.process_time = str(timeout)

                if deserialize and hasattr(s, "deserialize"):
                    return s.deserialize()
                return s

            axon_list = axons if isinstance(axons, (list, tuple)) else [axons]
            return await asyncio.gather(
                *(single_axon_response(i, target_axon) for i, target_axon in enumerate(axon_list))
            )

        results = await query_all_axons(streaming)
        if not isinstance(axons, (list, tuple)):
            return results[0]
        return results

    def __str__(self) -> str:
        return "MockDendrite({})".format(getattr(self.keypair, "ss58_address", "?"))
