import pytest
import bittensor as bt

from qbittensor.utils.request.JWTManager import JWTManager
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
