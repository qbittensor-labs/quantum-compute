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

import numpy as np
from unittest.mock import Mock

from qbittensor.base.utils.weight_utils import (
    process_weights_for_netuid,
    convert_weights_and_uids_for_emit,
    normalize_max_weight,
    U16_MAX,
)


def test_normalize_basic():
    x = np.array([0.1, 0.9, 0.0])
    y = normalize_max_weight(x, limit=0.5)
    assert abs(y.sum() - 1.0) < 1e-6
    assert y.max() <= 0.5 + 1e-6


def test_convert_to_uint16():
    uids = np.array([0, 1])
    weights = np.array([0.0, 1.0])
    uint_uids, uint_w = convert_weights_and_uids_for_emit(uids, weights)
    assert len(uint_uids) == 1
    assert uint_w[0] > 0


def _subtensor_with_hp(*, min_allowed_weights: int = 1, max_weight_limit: float = 1.0):
    class _HP:
        def min_allowed_weights(self, netuid: int):
            return min_allowed_weights

        def max_weight_limit(self, netuid: int):
            return max_weight_limit

    class _ST:
        hyperparameters = _HP()

    return _ST()


def test_process_weights_basic():
    uids = np.array([0, 1, 2])
    w = np.array([0.0, 0.5, 0.5], dtype=np.float32)
    p_uids, p_w = process_weights_for_netuid(
        uids=uids,
        weights=w,
        netuid=1,
        subtensor=_subtensor_with_hp(),
        metagraph=Mock(n=3),
    )
    assert len(p_uids) >= 1
    assert abs(p_w.sum() - 1.0) < 1e-5 or len(p_w) == 0


def test_process_weights_reads_hyperparameters():
    """Weights processing uses subtensor.hyperparameters.min/max_weight_limit."""
    uids = np.array([0, 1, 2])
    w = np.array([0.2, 0.5, 0.3], dtype=np.float32)
    p_uids, p_w = process_weights_for_netuid(
        uids=uids,
        weights=w,
        netuid=1,
        subtensor=_subtensor_with_hp(min_allowed_weights=1, max_weight_limit=1.0),
        metagraph=Mock(n=3),
    )
    assert len(p_uids) >= 1
    assert abs(float(p_w.sum()) - 1.0) < 1e-5


class TestConvertWeightsAndUidsForEmit:
    """Contract tests for the u16 quantization used for on-chain weight emission.

    Ported from enigma-staging for coverage parity on shared weight_utils.
    """

    def test_single_dust_with_dominant_treasury_sums_to_exactly_u16_max(self):
        """The classic off-by-2 case: treasury ~0.999975 + one dust 2.5e-5."""
        scores = np.array([0.999975, 0.0, 0.000025], dtype=np.float32)
        uids = np.array([87, 100, 171], dtype=np.int64)

        norm = np.linalg.norm(scores, ord=1)
        raw_weights = scores / norm

        uint_uids, uint_weights = convert_weights_and_uids_for_emit(
            uids=uids, weights=raw_weights
        )

        total = sum(uint_weights)
        assert total == U16_MAX, f"Expected sum {U16_MAX}, got {total}"
        assert total <= U16_MAX

        emitted = dict(zip([int(u) for u in uint_uids], uint_weights))
        assert emitted.get(171, 0) > 0
        assert emitted.get(171, 0) in (1, 2)

    def test_many_dust_weights_still_sum_leq_u16_max(self):
        """Stress case: 1 dominant + 49 tiny dust weights."""
        n = 50
        scores = np.zeros(n, dtype=np.float32)
        scores[0] = 1.0 - (n - 1) * 1e-5
        for i in range(1, n):
            scores[i] = 1e-5

        norm = np.linalg.norm(scores, ord=1)
        raw = scores / norm

        uint_uids, uint_weights = convert_weights_and_uids_for_emit(
            uids=np.arange(n), weights=raw
        )

        total = sum(uint_weights)
        assert total <= U16_MAX, f"Sum {total} exceeded U16_MAX"
        assert len(uint_weights) == n

    def test_all_weights_zero_returns_empty(self):
        scores = np.zeros(5, dtype=np.float32)
        uint_uids, uint_weights = convert_weights_and_uids_for_emit(
            uids=np.arange(5), weights=scores
        )
        assert uint_uids == []
        assert uint_weights == []

    def test_exact_u16_max_single_weight(self):
        """Edge case: exactly one weight of 1.0 after normalization."""
        scores = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        uint_uids, uint_weights = convert_weights_and_uids_for_emit(
            uids=np.array([0, 1, 2]), weights=scores
        )
        assert sum(uint_weights) == U16_MAX
        assert uint_weights[0] == U16_MAX
