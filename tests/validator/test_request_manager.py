import pytest

from qbittensor.utils.request.JWTManager import JWT
from qbittensor.utils.request.RequestManager import RequestManager
from qbittensor.utils.timestamping import timestamp
from tests.test_utils import get_mock_keypair
import pytest
from unittest import mock
from datetime import timedelta
import requests
from unittest.mock import Mock

#---------
# Fixtures
#---------

@pytest.fixture
def rm(monkeypatch):
    # Patch JWTManager.get_jwt to avoid real HTTP calls and always return a valid JWT
    fake_jwt = JWT(
        **{
            "access_token": "test_token",
            "expires_in": 300,
            "expiration_date": timestamp() + timedelta(seconds=300)
        }
    )
    monkeypatch.setattr(
        "qbittensor.utils.request.JWTManager.JWTManager.get_jwt",
        lambda self: fake_jwt
    )
    mock_keypair = get_mock_keypair()
    return RequestManager(mock_keypair)

#------
# Tests
#------

def test_check_error_code(rm):
    """Test the error code check"""
     # Test error codes (should return True)
    response_199 = Mock(spec=requests.Response)
    response_199.status_code = 199
    assert rm.check_error_code(response_199, "endpoint", "GET")
    
    response_301 = Mock(spec=requests.Response)
    response_301.status_code = 301
    assert rm.check_error_code(response_301, "endpoint", "GET")
    
    # Test success codes (should return False)
    response_200 = Mock(spec=requests.Response)
    response_200.status_code = 200
    assert not rm.check_error_code(response_200, "endpoint", "GET")
    
    response_299 = Mock(spec=requests.Response)
    response_299.status_code = 299
    assert not rm.check_error_code(response_299, "endpoint", "GET")

def test_get_header_mocks_jwt(rm):
    """Test that get_signed_header uses JWT and returns correct header"""
    headers = rm._get_header()
    assert isinstance(headers, dict)
    assert "Authorization" in headers
    assert headers["Authorization"] == "Bearer test_token"

def test_token_is_expired_expired_token(rm):
    """Test that get_signed_header refreshes JWT if expired"""
    expired_jwt: JWT = JWT(
        **{
            "access_token": "expired_token",
            "expires_in": 300,
            "expiration_date": timestamp() + timedelta(seconds=10)
        }
    )
    rm._jwt = expired_jwt
    assert rm._token_is_expired()

def test_token_is_expired_none_jwt(rm):
    """Test _token_is_expired returns True if JWT is None"""
    rm._jwt = None
    assert rm._token_is_expired()

def test_token_is_expired_valid_token(rm):
    """Test _token_is_expired returns False if token is valid"""
    fake_jwt: JWT = JWT(
        **{
            "access_token": "not_expired_token",
            "expires_in": 300,
            "expiration_date": timestamp() + timedelta(seconds=65)
        }
    )
    rm._jwt = fake_jwt
    assert not rm._token_is_expired()

def test_get_header_format(monkeypatch, rm):
    """Test _get_header returns correct format after JWT refresh"""
    # Patch _token_is_expired to True to force refresh
    monkeypatch.setattr(rm, "_token_is_expired", lambda: True)
    fake_jwt = mock.Mock()
    fake_jwt.access_token = "abc123"
    monkeypatch.setattr(rm._jwt_manager, "get_jwt", lambda: fake_jwt)
    headers = rm._get_header()
    assert headers["Authorization"] == "Bearer abc123"
