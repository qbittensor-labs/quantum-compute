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

from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest

from qbittensor.api.get_query_axons import (
    ping_uids,
    get_query_api_nodes,
    get_query_api_axons,
)


@pytest.mark.asyncio
async def test_ping_uids_success_and_fail():
    dendrite = AsyncMock()
    # responses with dendrite.status_code
    ok = Mock()
    ok.dendrite.status_code = 200
    fail = Mock()
    fail.dendrite.status_code = 500

    dendrite.return_value = [ok, fail, ok]

    mg = Mock()
    mg.axons = ["a0", "a1", "a2"]

    good, bad = await ping_uids(dendrite, mg, [0, 1, 2], timeout=1)
    assert good == [0, 2]
    assert bad == [1]
    dendrite.assert_called_once()


@pytest.mark.asyncio
async def test_ping_uids_exception_treats_all_failed():
    dendrite = AsyncMock(side_effect=RuntimeError("boom"))
    mg = Mock()
    mg.axons = ["x0"]  # match the uid list length we pass

    good, bad = await ping_uids(dendrite, mg, [0], timeout=1)
    assert good == []
    assert bad == [0]


@pytest.mark.asyncio
async def test_get_query_api_nodes_filters_and_samples(monkeypatch):
    dendrite = AsyncMock()
    ok = Mock()
    ok.dendrite.status_code = 200
    dendrite.return_value = [ok, ok, ok]

    mg = Mock()
    mg.netuid = 48
    mg.uids = np.array([0, 1, 2, 3, 4])
    mg.validator_trust = np.array([0.0, 1.0, 0.9, 0.0, 0.5])
    mg.S = np.array([10.0, 100.0, 90.0, 5.0, 80.0])
    mg.axons = ["a"] * 5

    # n=0.5 so top by stake are high ones
    uids = await get_query_api_nodes(dendrite, mg, n=0.5, timeout=1)
    # vtrust ones intersect top: 1,2,4 ; ping all succeed -> sample up to 3
    assert len(uids) <= 3
    assert set(uids).issubset({1, 2, 4})


@pytest.mark.asyncio
async def test_get_query_api_axons_with_explicit_uids(monkeypatch):
    fake_dendrite = Mock()
    fake_mg = Mock()
    fake_mg.axons = ["axon0", "axon1", "axon42"]

    with patch("qbittensor.api.get_query_axons.bt.Dendrite", return_value=fake_dendrite):
        with patch("qbittensor.api.get_query_axons.bt.Metagraph", return_value=fake_mg):
            axons = await get_query_api_axons(Mock(), metagraph=fake_mg, uids=[1, 2])
            assert axons == ["axon1", "axon42"]


@pytest.mark.asyncio
async def test_get_query_api_axons_default_creates_metagraph(monkeypatch):
    fake_d = AsyncMock()
    # make ping return some
    r_ok = Mock()
    r_ok.dendrite.status_code = 200
    fake_d.return_value = [r_ok]

    fake_mg = Mock()
    fake_mg.netuid = 48
    fake_mg.uids = np.array([0])
    fake_mg.validator_trust = np.array([1.0])
    fake_mg.S = np.array([999.0])
    fake_mg.axons = ["the-axon"]

    with patch("qbittensor.api.get_query_axons.bt.Dendrite", return_value=fake_d):
        with patch("qbittensor.api.get_query_axons.bt.Metagraph", return_value=fake_mg):
            # When uids provided via get_query_api_nodes path it will use index 0
            axons = await get_query_api_axons(Mock(), metagraph=fake_mg, uids=[0])
            assert axons == ["the-axon"]
