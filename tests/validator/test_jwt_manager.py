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

import pytest
import bittensor as bt

from qbittensor.utils.request.jwt_manager import JWTManager
from tests.test_utils import get_mock_keypair


@pytest.fixture
def jm():
    keypair: bt.Keypair = get_mock_keypair()
    return JWTManager(keypair)


def test_get_signed_header(jm):
    """Test that get_signed_header returns a dictionary with Authorization key"""
    headers = jm._get_signed_header()
    assert isinstance(headers, dict)
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Bearer ")


def test_signed_header_includes_netuid_and_node_type():
    """Signed TensorAuth JSON carries subnet from netuid and node_type."""
    import base64
    import json

    keypair = get_mock_keypair()
    jm = JWTManager(keypair, netuid=1, node_type="validator")
    headers = jm._get_signed_header()
    token = headers["Authorization"].split(" ", 1)[1]
    pad = "=" * (-len(token) % 4)
    payload = json.loads(base64.b64decode(token + pad))
    assert payload["subnet"] == 1
    assert payload["node_type"] == "validator"


def test_signed_header_defaults_node_type_miner_and_subnet_from_env(monkeypatch):
    import base64
    import json

    monkeypatch.setenv("NETUID", "7")
    keypair = get_mock_keypair()
    jm = JWTManager(keypair)
    headers = jm._get_signed_header()
    token = headers["Authorization"].split(" ", 1)[1]
    pad = "=" * (-len(token) % 4)
    payload = json.loads(base64.b64decode(token + pad))
    assert payload["subnet"] == 7
    assert payload["node_type"] == "miner"
