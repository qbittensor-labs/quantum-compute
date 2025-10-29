import pytest

from qbittensor.miner.providers.mock import MockProviderAdapter
from qbittensor.miner.runtime.registry import JobRegistry
from pkg.database.database_manager import DatabaseManager
from qbittensor.miner.miner_table_initializer import MinerTableInitializer


class DummyKeypair:
    def __init__(self):
        self.ss58_address = "5DummyHotkey11111111111111111111111111111111"


@pytest.fixture(autouse=True)
def _env_job_server(monkeypatch):
    monkeypatch.setenv("JOB_SERVER_URL", "http://localhost:9999")
    monkeypatch.setenv("API_VERSION", "1")
    monkeypatch.setenv("PROVIDER", "mock")
    monkeypatch.setenv("TENSORAUTH_URL", "http://localhost:9998")

    import qbittensor.miner.providers.registry as _preg
    monkeypatch.setattr(_preg, "get_adapter", lambda name=None: MockProviderAdapter())
    yield


@pytest.fixture
def temp_db(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    import pkg.database.database_manager as dm
    orig = dm.data_dir
    dm.data_dir = str(data_dir)
    try:
        yield data_dir
    finally:
        dm.data_dir = orig


@pytest.fixture
def db_manager(temp_db):
    dbm = DatabaseManager("miner_test")
    MinerTableInitializer(dbm).create_tables()
    return dbm


@pytest.fixture
def mock_adapter():
    return MockProviderAdapter()


@pytest.fixture
def registry(db_manager, mock_adapter):
    keypair = DummyKeypair()
    reg = JobRegistry(db=db_manager, keypair=keypair, poll_interval_s=0.01, adapter=mock_adapter)
    try:
        yield reg
    finally:
        reg.stop()


@pytest.fixture
def http_mock(monkeypatch):
    import requests

    class Resp:
        def __init__(self, status_code=200, text="OK", json_body=None):
            self.status_code = status_code
            self.text = text
            self._json = json_body

        def json(self):
            if self._json is None:
                return {"ok": True}
            return self._json

        def raise_for_status(self):
            if self.status_code < 200 or self.status_code >= 300:
                raise requests.HTTPError(response=self)

    def fake_get(url, *a, **k):
        base = url.split('?', 1)[0]
        if base.endswith("/v1/executions"):
            return Resp(204)
        return Resp(200, text="OPENQASM 2.0; // mock")

    def fake_put(url, *a, **k):
        return Resp(200, text="uploaded")

    def fake_post(url, *a, **k):
        if url.endswith("/v1/executions/upload"):
            return Resp(201, json_body={"upload_url": "http://s3/presigned", "id": "rid-1"})
        return Resp(200)

    def fake_patch(url, *a, **k):
        return Resp(200)

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.put", fake_put)
    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.patch", fake_patch)
    monkeypatch.setattr("requests.sessions.Session.get", lambda self, url, *a, **k: fake_get(url, *a, **k))
    monkeypatch.setattr("requests.sessions.Session.post", lambda self, url, *a, **k: fake_post(url, *a, **k))
    monkeypatch.setattr("requests.sessions.Session.patch", lambda self, url, *a, **k: fake_patch(url, *a, **k))
    # fallback here for case when code paths bypass get/post/patch
    def fake_request(self, method, url, *a, **k):
        m = (method or "").upper()
        if m == "GET":
            return fake_get(url, *a, **k)
        if m == "POST":
            return fake_post(url, *a, **k)
        if m == "PATCH":
            return fake_patch(url, *a, **k)
        return Resp(200)
    monkeypatch.setattr("requests.sessions.Session.request", fake_request)

    from qbittensor.utils.request.RequestManager import RequestManager as _RM
    def _rm_get(self, endpoint: str, params: dict = {}, additional_headers: list = []):
        if endpoint == "executions":
            return Resp(204)
        return Resp(200)
    monkeypatch.setattr(_RM, "get", _rm_get, raising=True)
    return True

import pytest
from datetime import datetime, timedelta, timezone

class _FakeJWT:
    def __init__(self) -> None:
        self.access_token = "test_access_token"
        self.expires_in = 3600
        self.expiration_date = datetime.now(timezone.utc) + timedelta(seconds=self.expires_in)


@pytest.fixture(autouse=True)
def _patch_env_and_jwt(monkeypatch):
    monkeypatch.setenv("JOB_SERVER_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("API_VERSION", "1")
    monkeypatch.setenv("TENSORAUTH_URL", "http://127.0.0.1:8081")

    from qbittensor.utils.request.JWTManager import JWTManager
    monkeypatch.setattr(JWTManager, "get_jwt", lambda self: _FakeJWT(), raising=True)

    yield


