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
from unittest.mock import patch

from qbittensor.validator.heartbeat import Heartbeat
from unittest.mock import Mock
from qbittensor.utils.services.telemetry import TelemetryService


@pytest.fixture
def mock_telemetry_service(monkeypatch):
    tel = Mock(spec=TelemetryService)
    return tel


def test_heartbeat_init_sets_timer(mock_telemetry_service):
    hb = Heartbeat(mock_telemetry_service)
    assert hb.timer is not None
    assert hb.telemetry_service is not None


def test_send_version_info_calls_telemetry(mock_telemetry_service):
    hb = Heartbeat(mock_telemetry_service)
    with patch.object(hb.telemetry_service, "vali_record_heartbeat") as mock_record:
        hb.send_version_info()
        mock_record.assert_called_once()
        # version should be a string
        call_args = mock_record.call_args[1]
        assert "version" in call_args
        assert isinstance(call_args["version"], str)


def test_get_version_returns_str(mock_telemetry_service):
    hb = Heartbeat(mock_telemetry_service)
    v = hb._get_version()
    assert isinstance(v, str)
    assert len(v) > 0
