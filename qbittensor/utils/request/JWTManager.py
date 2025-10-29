import base64
import json
from typing import Dict
import bittensor as bt
from dotenv import load_dotenv
import os
import sys
from time import time
from pydantic import BaseModel
import requests
from datetime import datetime, timedelta

from qbittensor.utils.request.utils import make_session
from qbittensor.utils.timestamping import timestamp


JWT_ENDPOINT: str = "token"

class KeycloakJWT(BaseModel):
    access_token: str
    expires_in: int

class JWT(KeycloakJWT):
    expiration_date: datetime

class JWTManager:

    def __init__(self, keypair: bt.Keypair) -> None:
        self._keypair: bt.Keypair = keypair
        self._timeout: float = 7.0
        self._session: requests.Session = make_session(allowed_methods=["GET"])
        self._tensorauth_url: str = ""

        load_dotenv()
        try:
            tensorauth_url: str | None = os.getenv("TENSORAUTH_URL")
            if tensorauth_url is None:
                raise ValueError("TENSORAUTH_URL environment variable not set")
        except (ValueError, TypeError):
            bt.logging.error("❌ ERROR: You must provide TENSORAUTH_URL in the .env file.")
            sys.exit(1)
        self._tensorauth_url = tensorauth_url

    def get_jwt(self) -> JWT:
        """Fetch JWT from tensorauth service using signed header"""
        bt.logging.trace(f" ☎️  Contacting tensorauth service for a JWT")
        now: datetime = timestamp()
        response = self._session.get(f"{self._tensorauth_url}/{JWT_ENDPOINT}", headers=self._get_signed_header(), timeout=self._timeout)
        response.raise_for_status()
        token_data = response.json()
        if not isinstance(token_data, dict):
            bt.logging.error(f"❌ ERROR: JWT response is not a dictionary: {token_data}")
            raise ValueError("JWT response is not a dictionary")
        try:
            token: KeycloakJWT = KeycloakJWT(**{str(k): v for k, v in token_data.items()})
        except Exception as e:
            bt.logging.error(f"❌ ERROR: Failed to parse JWT response: {e}")
            raise e
        bt.logging.trace(f"✅ Received JWT from {self._tensorauth_url}/{JWT_ENDPOINT}")
        expiration_date: datetime = now + timedelta(seconds=token.expires_in)
        bt.logging.trace(f"    - Token expires at {expiration_date.isoformat()} (in {token.expires_in} seconds)")
        return JWT(**token.model_dump(by_alias=True), expiration_date=expiration_date)

    def _get_signed_header(self) -> Dict[str, str]:
        """Create request header with signature, timestamp, hotkey"""
        timestamp = str(int(time()))
        signature_bytes: bytes = self._keypair.sign(self._keypair.ss58_address.encode("utf-8"))
        signature_b64: str = base64.b64encode(signature_bytes).decode("utf-8")
        token_json: dict = {
            "hotkey": self._keypair.ss58_address,
            "timestamp": timestamp,
            "signature": signature_b64
        }
        token: str = base64.b64encode(json.dumps(token_json).encode("utf-8")).decode('utf-8')
        return {
            "Authorization": f"Bearer {token}",
        }
