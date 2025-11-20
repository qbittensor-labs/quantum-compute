import bittensor as bt
from typing import Dict, List, Tuple
from dotenv import load_dotenv
import os
import sys
import requests
from datetime import datetime, timedelta

from qbittensor.utils.request.JWTManager import JWT, JWTManager
from qbittensor.utils.request.utils import make_session
from qbittensor.utils.timestamping import timestamp


JWT_EXPIRATION_BUFFER: timedelta = timedelta(minutes=1)

class RequestManager:

    def __init__(self, keypair: bt.Keypair, node_type: str = "miner" or "validator", network: str = "") -> None:
        self._keypair: bt.Keypair = keypair
        self._service_name = f"bittensor.sn48.{node_type}"
        self._network = network
        self._timeout: float = 7.0
        self._job_server_url: str = ""
        self._jwt_manager: JWTManager = JWTManager(keypair)
        self._jwt: JWT = self._jwt_manager.get_jwt()
        self._session: requests.Session = make_session(allowed_methods=["GET", "POST", "PATCH"])

        load_dotenv()

        # Setup job server url
        try:
            job_server_url: str | None = os.getenv("JOB_SERVER_URL")
            if job_server_url is None:
                raise ValueError("JOB_SERVER_URL environment variable not set")
        except (ValueError, TypeError):
            print("❌ ERROR: You must provide JOB_SERVER_URL in the .env file.")
            sys.exit(1)
        self._job_server_url: str = job_server_url

        # Setup telemetry url
        self.telemetry_base_url = os.environ.get("METRICS_API_URL", "https://telemetry.openquantum.com")

        # Setup api version
        try:
            api_version: str | None = os.getenv("API_VERSION")
            if api_version is None:
                raise ValueError("API_VERSION environment variable not set")
        except (ValueError, TypeError):
            print("❌ ERROR: You must provide API_VERSION in the .env file.")
            sys.exit(1)
        self._api_version: str = f"v{api_version}"

    def get(self, endpoint: str, params: Dict = {}, additional_headers: List[Tuple[str, str]] = [], ignore_codes: List[int] = []) -> requests.Response:
        """Make a GET request to the job server with signed header"""
        headers = self._get_header()
        for key, value in additional_headers:
            headers[key] = value
        full_url: str = self._build_url(endpoint)
        response: requests.Response = self._session.get(full_url, headers=headers, params=params, timeout=self._timeout)
        self.check_error_code(response, full_url, "GET", ignore_codes=ignore_codes)
        return response

    def post(self, endpoint: str, json: Dict = {}, params: Dict = {}, additional_headers: List[Tuple[str, str]] = [], ignore_codes: List[int] = []) -> requests.Response:
        """Make a POST request to the job server with signed header"""
        headers = self._get_header()
        for key, value in additional_headers:
            headers[key] = value
        full_url: str = self._build_url(endpoint)
        response: requests.Response = self._session.post(full_url, json=json, headers=headers, params=params, timeout=self._timeout)
        self.check_error_code(response, full_url, "POST", ignore_codes=ignore_codes)
        return response

    def post_telemetry(self, endpoint: str, json: Dict = {}, params: Dict = {}, ignore_codes: List[int] = []) -> requests.Response:
        """Make a POST request to the job server with signed header"""
        headers = self._get_header()
        headers["X-Service-Name"] = self._service_name
        headers["X-Network"] = self._network
        full_url: str = self._build_telemetry_url(endpoint)
        response: requests.Response = self._session.post(full_url, json=json, headers=headers, params=params, timeout=self._timeout)
        self.check_error_code(response, full_url, "POST", ignore_codes=ignore_codes)
        return response

    def patch(self, endpoint: str, json: Dict, params: Dict = {}, ignore_codes: List[int] = []) -> requests.Response:
        """Make a PATCH request to the job server with signed header"""
        headers = self._get_header()
        full_url: str = self._build_url(endpoint)
        response: requests.Response = self._session.patch(full_url, json=json, headers=headers, params=params, timeout=self._timeout)
        self.check_error_code(response, full_url, "PATCH", ignore_codes=ignore_codes)
        return response

    def check_error_code(self, response: requests.Response, url: str, method: str, ignore_codes: List[int] = []) -> bool:
        """Return true if status code is non-200"""
        status_code = response.status_code
        is_error_code = status_code < 200 or status_code > 299
        if is_error_code:
            if status_code not in ignore_codes:
                bt.logging.trace(f"❗ Received error from server for '{method} {url}' code: {status_code} - {response.text}")
        else:
            if status_code not in ignore_codes:
                bt.logging.trace(f"✅ {method} request to '{url}' successful with status code {status_code}")
        return is_error_code
    
    def _build_url(self, endpoint: str) -> str:
        """Build full endpoint url"""
        return f"{self._job_server_url}/{self._api_version}/{endpoint}"

    def _build_telemetry_url(self, endpoint: str) -> str:
        """Build full telemetry endpoint url"""
        return f"{self.telemetry_base_url}/v1/{endpoint}"

    def _get_header(self) -> Dict[str, str]:
        """Create request header with signature, timestamp, hotkey"""
        if self._token_is_expired():
            bt.logging.trace("🔑 JWT expired, fetching a new one")
            self._jwt: JWT = self._jwt_manager.get_jwt()
        return {
            "Authorization": f"Bearer {self._jwt.access_token}",
        }
    
    def _token_is_expired(self) -> bool:
        """Check if the current JWT is expired"""
        if self._jwt is None:
            return True
        now: datetime = timestamp()
        return now >= (self._jwt.expiration_date - JWT_EXPIRATION_BUFFER)
