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

import bittensor as bt
from typing import Any, Dict, List, Tuple
import requests
from datetime import datetime, timedelta

from qbittensor.utils.request.jwt_manager import JWT, JWTManager
from qbittensor.utils.request.utils import make_session
from qbittensor.utils.time import timestamp
from qbittensor.utils.env import get_api_config, load_env


JWT_EXPIRATION_BUFFER: timedelta = timedelta(minutes=1)


class RequestManager:

    def __init__(
        self,
        keypair: Any,
        *,
        node_type: str = "miner",
        network: str = "",
        job_api_url: str | None = None,
        tensorauth_url: str | None = None,
        telemetry_api_url: str | None = None,
        api_version: str | None = None,
        netuid: int | None = None,
    ) -> None:
        self._keypair: Any = keypair
        self._node_type = node_type
        self._service_name = f"bittensor.sn48.{node_type}"
        self._network = network
        self._timeout: float = 7.0
        self._job_server_url: str = ""
        self._jwt_manager: JWTManager = JWTManager(
            keypair,
            tensorauth_url=tensorauth_url,
            netuid=netuid,
            node_type=node_type,
        )
        self._jwt: JWT = self._jwt_manager.get_jwt()
        self._session: requests.Session = make_session(allowed_methods=["GET", "POST", "PATCH"])

        load_env()
        cfg = get_api_config()

        # Setup job server url (prefer explicit, then env/config)
        self._job_server_url = job_api_url or cfg.job_api_url
        if not self._job_server_url:
            print("❌ ERROR: JOB_API_URL or JOB_SERVER_URL must be provided (via constructor, env, or config).")
            raise ValueError("JOB_API_URL or JOB_SERVER_URL is required")

        # Setup telemetry url
        self.telemetry_base_url = telemetry_api_url or cfg.telemetry_api_url or "https://telemetry.openquantum.com"

        # Setup api version
        version = api_version or cfg.api_version or "1"
        self._api_version: str = f"v{version}"

    def get(self, endpoint: str, params: Dict = {}, additional_headers: List[Tuple[str, str]] = [
    ], ignore_codes: List[int] = []) -> requests.Response:
        """Make a GET request to the job server with signed header"""
        headers = self._get_header()
        for key, value in additional_headers:
            headers[key] = value
        full_url: str = self._build_url(endpoint)
        response: requests.Response = self._session.get(full_url, headers=headers, params=params, timeout=self._timeout)
        self.check_error_code(response, full_url, "GET", ignore_codes=ignore_codes)
        return response

    def post(self, endpoint: str, json: Dict = {}, params: Dict = {},
             additional_headers: List[Tuple[str, str]] = [], ignore_codes: List[int] = []) -> requests.Response:
        """Make a POST request to the job server with signed header"""
        headers = self._get_header()
        for key, value in additional_headers:
            headers[key] = value
        full_url: str = self._build_url(endpoint)
        response: requests.Response = self._session.post(
            full_url, json=json, headers=headers, params=params, timeout=self._timeout)
        self.check_error_code(response, full_url, "POST", ignore_codes=ignore_codes)
        return response

    def post_telemetry(self, endpoint: str, json: Dict = {}, params: Dict = {},
                       ignore_codes: List[int] = []) -> requests.Response:
        """Make a POST request to the job server with signed header"""
        headers = self._get_header()
        headers["X-Service-Name"] = self._service_name
        headers["X-Network"] = self._network
        full_url: str = self._build_telemetry_url(endpoint)
        response: requests.Response = self._session.post(
            full_url, json=json, headers=headers, params=params, timeout=self._timeout)
        self.check_error_code(response, full_url, "POST", ignore_codes=ignore_codes)
        return response

    def patch(self, endpoint: str, json: Dict, params: Dict = {}, ignore_codes: List[int] = []) -> requests.Response:
        """Make a PATCH request to the job server with signed header"""
        headers = self._get_header()
        full_url: str = self._build_url(endpoint)
        response: requests.Response = self._session.patch(
            full_url, json=json, headers=headers, params=params, timeout=self._timeout)
        self.check_error_code(response, full_url, "PATCH", ignore_codes=ignore_codes)
        return response

    def check_error_code(
            self,
            response: requests.Response,
            url: str,
            method: str,
            ignore_codes: List[int] = []) -> bool:
        """Return true if status code is non-200"""
        status_code = response.status_code
        is_error_code = status_code < 200 or status_code > 299
        if is_error_code:
            if status_code not in ignore_codes:
                bt.logging.trace(
                    f"❗ Received error from server for '{method} {url}' code: {status_code} - {response.text}")
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
