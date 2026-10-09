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

import random
import bittensor as bt
import numpy as np
from typing import List


def check_uid_availability(metagraph: "bt.Metagraph", uid: int) -> bool:
    """True when the axon is serving. Permit and stake do not exclude a uid."""
    if not metagraph.axons[uid].is_serving:
        return False
    return True


def get_random_uids(self, k: int, exclude: List[int] = None) -> np.ndarray:
    """Returns k available random uids from the metagraph.
    Args:
        k (int): Number of uids to return.
        exclude (List[int]): List of uids to exclude from the random sampling.
    Returns:
        uids (np.ndarray): Randomly sampled available uids.
    Notes:
        If `k` is larger than the number of available `uids`, set `k` to the number of available `uids`.
    """
    candidate_uids = []
    avail_uids = []

    for uid in range(self.metagraph.n.item()):
        uid_is_available = check_uid_availability(self.metagraph, uid)
        uid_is_not_excluded = exclude is None or uid not in exclude

        if uid_is_available:
            avail_uids.append(uid)
            if uid_is_not_excluded:
                candidate_uids.append(uid)
    # If k is larger than the number of available uids, set k to the number of available uids.
    k = min(k, len(avail_uids))
    # Check if candidate_uids contain enough for querying, if not grab all avaliable uids
    available_uids = candidate_uids
    if len(candidate_uids) < k:
        available_uids += random.sample(
            [uid for uid in avail_uids if uid not in candidate_uids],
            k - len(candidate_uids),
        )
    uids = np.array(random.sample(available_uids, k))
    return uids


def is_valid_miner_axon(axon: "bt.AxonInfo") -> bool:
    """
    Returns True only for axons we should actually attempt to connect to.

    Rejects:
    - Axons that are not currently serving
    - 0.0.0.0 (and empty) IPs — these are placeholders and will never succeed
    - port 0 or None (unannounced)
    """
    if axon is None:
        return False
    if not getattr(axon, "is_serving", False):
        return False

    ip = (getattr(axon, "ip", "") or "").strip()
    if ip in ("0.0.0.0", "0.0.0.0.0", "", "0.0.0"):
        return False

    port = getattr(axon, "port", 0)
    if not port or port == 0:
        return False

    return True
