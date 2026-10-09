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

"""
Unit tests for qbittensor.utils.uids helper functions.

Focus: is_valid_miner_axon — the guard that prevents the validator from
attempting to contact 0.0.0.0 or otherwise invalid miner axons.
"""

from unittest.mock import Mock

from qbittensor.utils.uids import check_uid_availability, is_valid_miner_axon


class TestIsValidMinerAxon:
    """Tests for the axon validity guard used by NextMiner."""

    def test_rejects_none(self):
        assert is_valid_miner_axon(None) is False

    def test_rejects_non_serving(self):
        axon = Mock()
        axon.is_serving = False
        axon.ip = "1.2.3.4"
        axon.port = 12345
        assert is_valid_miner_axon(axon) is False

    def test_rejects_zero_ip_variants(self):
        bad_ips = ["0.0.0.0", "0.0.0.0.0", "0.0.0", "", None]
        for ip in bad_ips:
            axon = Mock()
            axon.is_serving = True
            axon.ip = ip
            axon.port = 12345
            assert is_valid_miner_axon(axon) is False, f"Failed for ip={ip!r}"

    def test_rejects_zero_or_none_port(self):
        for port in (0, None):
            axon = Mock()
            axon.is_serving = True
            axon.ip = "1.2.3.4"
            axon.port = port
            assert is_valid_miner_axon(axon) is False, f"Failed for port={port!r}"

    def test_accepts_normal_axon(self):
        axon = Mock()
        axon.is_serving = True
        axon.ip = "203.0.113.42"
        axon.port = 8091
        assert is_valid_miner_axon(axon) is True

    def test_accepts_localhost_for_testing(self):
        """localhost is unusual on mainnet but should be valid for local testing."""
        axon = Mock()
        axon.is_serving = True
        axon.ip = "127.0.0.1"
        axon.port = 8091
        assert is_valid_miner_axon(axon) is True

    def test_missing_attributes_are_treated_as_invalid(self):
        """If an axon is missing expected attributes, treat it as invalid."""
        axon = Mock(spec=[])  # no attributes at all
        assert is_valid_miner_axon(axon) is False

    def test_uses_getattr_defaults_safely(self):
        """Ensure the implementation doesn't blow up on weird axon objects."""
        axon = object()  # plain object with no attributes
        assert is_valid_miner_axon(axon) is False


class TestCheckUidAvailability:
    def test_serving_permitted_high_stake_is_available(self):
        mg = Mock()
        axon = Mock()
        axon.is_serving = True
        mg.axons = [axon]
        mg.validator_permit = [True]
        mg.S = [30_528.0]
        assert check_uid_availability(mg, 0) is True

    def test_not_serving_is_unavailable(self):
        mg = Mock()
        axon = Mock()
        axon.is_serving = False
        mg.axons = [axon]
        assert check_uid_availability(mg, 0) is False
