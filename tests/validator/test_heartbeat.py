import pytest
from unittest.mock import patch

from qbittensor.validator.heartbeat import Heartbeat
from qbittensor.utils.request.RequestManager import RequestManager
from qbittensor.utils.timestamping import timestamp
from tests.test_utils import get_mock_keypair


@pytest.fixture
def mock_request_manager(monkeypatch):
    keypair = get_mock_keypair()
    rm = RequestManager(keypair)
    # JWT is patched globally in conftest.py
    return rm


def test_heartbeat_init_sets_timer(mock_request_manager):
    hb = Heartbeat(mock_request_manager)
    assert hb.timer is not None
    assert hb.telemetry_service is not None


def test_send_version_info_calls_telemetry(mock_request_manager):
    hb = Heartbeat(mock_request_manager)
    with patch.object(hb.telemetry_service, "vali_record_heartbeat") as mock_record:
        hb.send_version_info()
        mock_record.assert_called_once()
        # version should be a string
        call_args = mock_record.call_args[1]
        assert "version" in call_args
        assert isinstance(call_args["version"], str)


def test_get_version_returns_str(mock_request_manager):
    hb = Heartbeat(mock_request_manager)
    v = hb._get_version()
    assert isinstance(v, str)
    assert len(v) > 0
