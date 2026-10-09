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

import os
import random
import time
from typing import Optional

import bittensor as bt
from pydantic import BaseModel, ConfigDict

from qbittensor.database.database_manager import DatabaseManager
from qbittensor.utils.env import env_csv
from qbittensor.utils.uids import is_valid_miner_axon
from qbittensor.validator.miner_manager.capabilities import (
    get_placeable_classes,
    has_capability_record,
    is_banned,
)

_DEFAULT_MIN_STAKE_ALPHA = 5000.0
_DEFAULT_DISPATCH_STAKE_EXPONENT = 1.0
_TIMEOUTS_BEFORE_BACKOFF = 2
_BACKOFF_MIN_S = 45 * 60.0
_BACKOFF_MAX_S = 75 * 60.0
_HEARTBEAT_BACKOFF_MIN_S = 60.0
_HEARTBEAT_BACKOFF_MAX_S = 120.0


class BasicMiner(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    hotkey: str
    uid: int
    axon: bt.AxonInfo

    def __repr__(self) -> str:
        return f"BasicMiner(hotkey={self.hotkey}, uid={self.uid}, axon={self.axon})"


class NextMiner:

    def __init__(
        self,
        metagraph: bt.Metagraph,
        skip_hotkeys: Optional[set[str]] = None,
        rng: Optional[random.Random] = None,
        stake_exponent: Optional[float] = None,
        min_stake_alpha: Optional[float] = None,
    ) -> None:
        self.metagraph = metagraph
        self.skip_hotkeys = set(skip_hotkeys or ())
        self._index = 0
        self._rng = rng if rng is not None else random.Random()
        if stake_exponent is None:
            try:
                stake_exponent = float(
                    os.getenv("DISPATCH_STAKE_EXPONENT")
                    or str(_DEFAULT_DISPATCH_STAKE_EXPONENT)
                )
            except ValueError:
                stake_exponent = _DEFAULT_DISPATCH_STAKE_EXPONENT
        self.stake_exponent = float(stake_exponent)
        if min_stake_alpha is None:
            try:
                min_stake_alpha = float(
                    os.getenv("WEIGHT_MIN_MINER_STAKE_ALPHA") or str(_DEFAULT_MIN_STAKE_ALPHA)
                )
            except ValueError:
                min_stake_alpha = _DEFAULT_MIN_STAKE_ALPHA
        self.min_stake_alpha = max(0.0, float(min_stake_alpha))
        self._timeouts: dict[str, int] = {}
        self._backoff_until: dict[str, float] = {}
        self._heartbeat_backoff_until: dict[str, float] = {}

    def get_next_miner(
        self, only_hotkeys: Optional[set[str]] = None
    ) -> BasicMiner | None:
        """Return the next miner with a connectable axon, or None if none are valid.

        Walks the metagraph round-robin, skipping non-serving, 0.0.0.0, and
        port-0 axons (``is_valid_miner_axon``). A validator permit does not
        exclude a hotkey.

        After one full pass with no valid candidate, returns None so the forward
        loop can exit.
        """
        n = len(self.metagraph.hotkeys)
        if n == 0 or (only_hotkeys is not None and len(only_hotkeys) == 0):
            self._index = 0
            return None
        # Clamp in case the metagraph shrank since the last call
        if self._index >= n:
            self._index = 0

        for _ in range(n):
            uid = self._index
            try:
                hotkey: str = self.metagraph.hotkeys[uid]
                axon: bt.AxonInfo = self._get_axon_from_metagraph(uid)

                if hotkey in self.skip_hotkeys:
                    continue

                if not is_valid_miner_axon(axon):
                    ip = getattr(axon, "ip", "unknown")
                    port = getattr(axon, "port", 0)
                    serving = getattr(axon, "is_serving", False)
                    bt.logging.debug(
                        f"⏭️  Skipping UID {uid} ({hotkey[:8]}...) — invalid axon "
                        f"ip={ip} port={port} serving={serving}"
                    )
                    continue

                if self.is_backed_off(hotkey):
                    continue
                if only_hotkeys is not None and hotkey not in only_hotkeys:
                    continue

                return BasicMiner(hotkey=hotkey, uid=uid, axon=axon)
            finally:
                self._increment_miner_index(n)

        return None

    def get_next_miner_for_class(
        self,
        short_code: Optional[str],
        db: DatabaseManager,
        only_hotkeys: Optional[set[str]] = None,
    ) -> Optional[BasicMiner]:
        """Pick with probability proportional to stake**exponent (default 1).

        Uncached miners stay eligible when PUBLIC_BACKEND_CLASSES is set.
        """
        placeable = get_placeable_classes(db)
        allowlist = env_csv("PUBLIC_BACKEND_CLASSES")
        allow = set(allowlist) if allowlist else None

        n = len(self.metagraph.hotkeys)
        if n == 0 or (only_hotkeys is not None and len(only_hotkeys) == 0):
            self._index = 0
            return None

        eligible: list[BasicMiner] = []
        for uid in range(n):
            hotkey: str = self.metagraph.hotkeys[uid]
            axon: bt.AxonInfo = self._get_axon_from_metagraph(uid)

            if hotkey in self.skip_hotkeys:
                continue
            if not is_valid_miner_axon(axon):
                continue
            if is_banned(db, hotkey):
                bt.logging.debug(
                    f"⏭️  Skipping UID {uid} ({hotkey[:8]}...) — locally banned"
                )
                continue
            if self.is_backed_off(hotkey):
                continue
            if only_hotkeys is not None and hotkey not in only_hotkeys:
                continue
            try:
                stake = max(0.0, float(self.metagraph.S[uid]))
            except Exception:
                stake = 0.0
            if stake < self.min_stake_alpha:
                continue

            classes = list(placeable.get(hotkey) or [])
            if classes:
                if allow is not None:
                    classes = [c for c in classes if c in allow]
                if not classes:
                    continue
            elif allowlist and not has_capability_record(db, hotkey):
                classes = list(allowlist)
            else:
                continue
            if short_code and short_code not in classes:
                continue

            eligible.append(BasicMiner(hotkey=hotkey, uid=uid, axon=axon))

        return self._pick_by_stake(eligible)

    def _pick_by_stake(self, eligible: list[BasicMiner]) -> Optional[BasicMiner]:
        if not eligible:
            return None
        weights: list[float] = []
        for miner in eligible:
            try:
                stake = max(0.0, float(self.metagraph.S[miner.uid]))
            except Exception:
                stake = 0.0
            if self.stake_exponent == 0:
                weights.append(1.0)
            elif stake <= 0:
                weights.append(0.0)
            else:
                weights.append(stake ** self.stake_exponent)
        total = sum(weights)
        if total <= 0:
            return self._rng.choice(eligible)
        return self._rng.choices(eligible, weights=weights, k=1)[0]

    def list_serving_miners(
        self,
        db: Optional[DatabaseManager] = None,
        *,
        heartbeat_hotkeys: Optional[set[str]] = None,
    ) -> list[BasicMiner]:
        """Serving miners. Backed-off hotkeys stay only for an in-flight heartbeat retry."""
        n = len(self.metagraph.hotkeys)
        keep = heartbeat_hotkeys or set()
        out: list[BasicMiner] = []
        for uid in range(n):
            hotkey: str = self.metagraph.hotkeys[uid]
            axon: bt.AxonInfo = self._get_axon_from_metagraph(uid)
            if hotkey in self.skip_hotkeys:
                continue
            if not is_valid_miner_axon(axon):
                continue
            if self.is_backed_off(hotkey):
                if hotkey not in keep or self.is_heartbeat_backed_off(hotkey):
                    continue
            if db is not None and is_banned(db, hotkey):
                continue
            out.append(BasicMiner(hotkey=hotkey, uid=uid, axon=axon))
        return out

    def _assignment_backoff_active(self, hotkey: str) -> bool:
        """True while the 45–75 minute skip is in force. An elapsed skip clears its strikes."""
        until = self._backoff_until.get(hotkey)
        if until is None:
            return False
        if time.time() >= until:
            self._backoff_until.pop(hotkey, None)
            self._timeouts.pop(hotkey, None)
            return False
        return True

    def is_backed_off(self, hotkey: str) -> bool:
        return self._assignment_backoff_active(hotkey)

    def is_heartbeat_backed_off(self, hotkey: str) -> bool:
        until = self._heartbeat_backoff_until.get(hotkey)
        if until is None:
            return False
        if time.time() >= until:
            self._heartbeat_backoff_until.pop(hotkey, None)
            return False
        return True

    def record_success(self, hotkey: str) -> None:
        self._timeouts.pop(hotkey, None)
        self._backoff_until.pop(hotkey, None)
        self._heartbeat_backoff_until.pop(hotkey, None)

    def record_timeout(self, hotkey: str, *, inflight: bool = False) -> Optional[float]:
        self._assignment_backoff_active(hotkey)
        n = self._timeouts.get(hotkey, 0) + 1
        self._timeouts[hotkey] = n
        if n >= _TIMEOUTS_BEFORE_BACKOFF:
            delay = self._rng.uniform(_BACKOFF_MIN_S, _BACKOFF_MAX_S)
            self._backoff_until[hotkey] = time.time() + delay
            if inflight:
                heartbeat = self._rng.uniform(
                    _HEARTBEAT_BACKOFF_MIN_S, _HEARTBEAT_BACKOFF_MAX_S
                )
                self._heartbeat_backoff_until[hotkey] = time.time() + heartbeat
                bt.logging.info(
                    f"Backing off {hotkey[:8]}... for {delay:.0f}s "
                    f"(heartbeat retry {heartbeat:.0f}s, in-flight job) "
                    f"after {n} dendrite timeouts"
                )
            else:
                bt.logging.info(
                    f"Backing off {hotkey[:8]}... for {delay:.0f}s after {n} dendrite timeouts"
                )
            return delay
        return None

    def _get_axon_from_metagraph(self, uid: int) -> bt.AxonInfo:
        """Gets the axon associated with a miner"""
        return self.metagraph.axons[uid]

    def _increment_miner_index(self, n: int | None = None):
        """Maintain the index by incrementing, wrapping at metagraph size."""
        size = n if n is not None else len(self.metagraph.hotkeys)
        if size <= 0:
            self._index = 0
            return
        self._index = (self._index + 1) % size
