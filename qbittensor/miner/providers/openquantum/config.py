# The MIT License (MIT)
# Copyright © 2026 qBitTensor Labs

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request

from pydantic import BaseModel, PrivateAttr

from qbittensor.utils.env import DEFAULT_JOB_API_URL, load_env

DEFAULT_KEYCLOAK_URL = "https://id.openquantum.com"
DEFAULT_KEYCLOAK_REALM = "platform"

PRIVATE_PLAN_ID = "f83fd52f-c691-470f-9521-26b81c4e53bd"
STANDARD_PRIORITY_ID = "0f7b91a3-d1bf-46fb-af9c-55b77fa72bed"
DEFAULT_SUBCATEGORY = "oth:oth"
DEFAULT_MIN_CREDITS = 50.0
DEFAULT_MANAGEMENT_URL = "https://management.openquantum.com"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


class OpenQuantumConfig(BaseModel):
    access_token: str | None
    organization_id: str | None
    scheduler_url: str
    management_url: str
    dry_run: bool
    min_credits: float
    queue_priority_id: str
    execution_plan_id: str
    subcategory_id: str
    http_timeout_s: int
    client_id: str | None = None
    client_secret: str | None = None
    keycloak_url: str = DEFAULT_KEYCLOAK_URL
    keycloak_realm: str = DEFAULT_KEYCLOAK_REALM
    _cached_token: str | None = PrivateAttr(default=None)
    _cached_expires_at: float = PrivateAttr(default=0.0)
    _token_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def has_api_credentials(self) -> bool:
        if self.access_token:
            return True
        return bool(self.client_id and self.client_secret)

    def bearer_token(self, *, force: bool = False) -> str | None:
        """Return a bearer token. An SDK key is refreshed before it expires."""
        if self.client_id and self.client_secret:
            with self._token_lock:
                if (
                    not force
                    and self._cached_token
                    and time.time() + 30 < self._cached_expires_at
                ):
                    return self._cached_token
                self._fetch_client_credentials()
                return self._cached_token
        return self.access_token

    def _fetch_client_credentials(self) -> None:
        url = (
            f"{self.keycloak_url.rstrip('/')}/realms/{self.keycloak_realm}"
            "/protocol/openid-connect/token"
        )
        body = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        ).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        with urllib.request.urlopen(req, timeout=self.http_timeout_s) as resp:
            payload = json.loads(resp.read().decode())
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("Keycloak token response missing access_token")
        self._cached_token = str(token)
        self._cached_expires_at = time.time() + int(payload.get("expires_in") or 300)

    @classmethod
    def from_env(cls, strict: bool = True) -> "OpenQuantumConfig":
        load_env()

        def _get(key: str) -> str | None:
            raw = os.getenv(key)
            return raw.strip() if raw and raw.strip() else None

        dry_run = _truthy(_get("OPENQUANTUM_DRY_RUN"))
        token = _get("OPENQUANTUM_ACCESS_TOKEN")
        client_id = _get("OPENQUANTUM_CLIENT_ID")
        client_secret = _get("OPENQUANTUM_CLIENT_SECRET")
        org = _get("OPENQUANTUM_ORGANIZATION_ID")
        scheduler = (
            _get("OPENQUANTUM_SCHEDULER_URL")
            or _get("JOB_API_URL")
            or _get("JOB_SERVER_URL")
            or DEFAULT_JOB_API_URL
        )
        management = _get("OPENQUANTUM_MANAGEMENT_URL") or DEFAULT_MANAGEMENT_URL
        try:
            min_credits = float(_get("OPENQUANTUM_MIN_CREDITS") or DEFAULT_MIN_CREDITS)
        except ValueError:
            min_credits = DEFAULT_MIN_CREDITS
        try:
            timeout_s = int(_get("OPENQUANTUM_HTTP_TIMEOUT_S") or "30")
        except ValueError:
            timeout_s = 30

        if strict and not dry_run:
            missing = []
            if not token and not (client_id and client_secret):
                missing.append("OPENQUANTUM_CLIENT_ID and OPENQUANTUM_CLIENT_SECRET")
            if not org:
                missing.append("OPENQUANTUM_ORGANIZATION_ID")
            if missing:
                raise RuntimeError(
                    "Open Quantum miner requires "
                    + ", ".join(missing)
                    + " unless OPENQUANTUM_DRY_RUN=1"
                )

        return cls(
            access_token=token,
            client_id=client_id,
            client_secret=client_secret,
            keycloak_url=_get("OPENQUANTUM_KEYCLOAK_URL") or DEFAULT_KEYCLOAK_URL,
            keycloak_realm=_get("OPENQUANTUM_KEYCLOAK_REALM") or DEFAULT_KEYCLOAK_REALM,
            organization_id=org,
            scheduler_url=scheduler.rstrip("/"),
            management_url=management.rstrip("/"),
            dry_run=dry_run,
            min_credits=min_credits,
            queue_priority_id=_get("OPENQUANTUM_QUEUE_PRIORITY_ID") or STANDARD_PRIORITY_ID,
            execution_plan_id=_get("OPENQUANTUM_EXECUTION_PLAN_ID") or PRIVATE_PLAN_ID,
            subcategory_id=_get("OPENQUANTUM_SUBCATEGORY_ID") or DEFAULT_SUBCATEGORY,
            http_timeout_s=timeout_s,
        )
