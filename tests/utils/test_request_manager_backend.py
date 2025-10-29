from qbittensor.utils.request.RequestManager import RequestManager
from tests.test_utils import get_mock_keypair


def test_header_contains_authorization_token(monkeypatch):
    monkeypatch.setenv("JOB_SERVER_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("API_VERSION", "1")
    monkeypatch.setenv("TENSORAUTH_URL", "http://127.0.0.1:8081")
    rm = RequestManager(get_mock_keypair())
    h = rm._get_header()
    assert "Authorization" in h
    assert isinstance(h["Authorization"], str) and h["Authorization"].startswith("Bearer ")


def test_patch_backend_calls_endpoint(monkeypatch):
    monkeypatch.setenv("JOB_SERVER_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("API_VERSION", "1")
    monkeypatch.setenv("TENSORAUTH_URL", "http://127.0.0.1:8081")
    rm = RequestManager(get_mock_keypair())

    called = {}

    class Resp:
        def __init__(self, code):
            self.status_code = code

    def fake_patch(self, url, *a, **k):
        called["url"] = url
        called["json"] = k.get("json")
        called["headers"] = k.get("headers", {})
        return Resp(200)

    # Patch Session.patch used by RequestManager
    import requests
    monkeypatch.setattr(requests.sessions.Session, "patch", fake_patch, raising=True)

    resp = rm.patch("backend", json={"isAvailable": True, "pricing": {"perTask": 0.03, "perShot": 0.001, "perMinute": 0.08}})
    assert resp.status_code == 200
    assert called.get("url", "").endswith("/backend")
    assert "Authorization" in called.get("headers", {})


