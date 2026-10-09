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

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from qbittensor.bt_compat import (
    Axon,
    _is_publishable_ip,
    resolve_axon_external_ip,
)


def test_loopback_is_not_publishable():
    assert _is_publishable_ip(None) is False
    assert _is_publishable_ip("") is False
    assert _is_publishable_ip("127.0.0.1") is False
    assert _is_publishable_ip("0.0.0.0") is False
    assert _is_publishable_ip("localhost") is False
    assert _is_publishable_ip("203.0.113.10") is True


def test_resolve_prefers_explicit_over_detect():
    with patch("qbittensor.bt_compat.detect_external_ip", return_value="198.51.100.2"):
        assert resolve_axon_external_ip("203.0.113.10") == "203.0.113.10"
        assert resolve_axon_external_ip("127.0.0.1") == "198.51.100.2"
        assert resolve_axon_external_ip(None) == "198.51.100.2"


def test_axon_init_copies_external_ip_from_config():
    config = SimpleNamespace(
        axon=SimpleNamespace(
            port=8091,
            ip="0.0.0.0",
            external_ip="203.0.113.10",
            external_port=8091,
        )
    )
    axon = Axon(wallet=Mock(), config=config)
    assert axon.external_ip == "203.0.113.10"


def test_serve_raises_when_no_publishable_ip():
    axon = Axon(wallet=Mock(), config=SimpleNamespace(axon=SimpleNamespace(external_ip=None)))
    with patch("qbittensor.bt_compat.detect_external_ip", return_value=None):
        with pytest.raises(RuntimeError, match="no publishable IP"):
            axon.serve(netuid=2, subtensor=Mock())


def test_serve_continues_when_subtensor_reports_failure():
    axon = Axon(wallet=Mock(), config=None)
    axon.external_ip = "203.0.113.10"
    subtensor = Mock()
    subtensor.execute.return_value = SimpleNamespace(success=False, error="Custom error 11")
    result = axon.serve(netuid=2, subtensor=subtensor)
    assert result is axon
    assert axon.external_ip == "203.0.113.10"
    subtensor.execute.assert_called_once()


def test_serve_publishes_detected_ip():
    axon = Axon(wallet=Mock(), config=None)
    subtensor = Mock()
    subtensor.execute.return_value = SimpleNamespace(success=True)
    with patch("qbittensor.bt_compat.detect_external_ip", return_value="203.0.113.10"):
        axon.serve(netuid=2, subtensor=subtensor)
    assert axon.external_ip == "203.0.113.10"
    subtensor.execute.assert_called_once()
