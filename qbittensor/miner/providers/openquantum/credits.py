# The MIT License (MIT)
# Copyright © 2026 qBitTensor Labs

from __future__ import annotations

from typing import Any, Optional, Tuple

import bittensor as bt
import requests

from .config import OpenQuantumConfig


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def get_remaining_credits(config: OpenQuantumConfig, timeout_s: int | None = None) -> Optional[float]:
    """Credit balance for the miner organization."""
    if config.dry_run:
        return None if not config.has_api_credentials() else 1_000_000.0
    token = config.bearer_token()
    if not token or not config.organization_id:
        return None
    url = (
        f"{config.management_url}/v1/organizations/"
        f"{config.organization_id}/transactions/balance"
    )
    try:
        resp = requests.get(
            url,
            headers=_auth_headers(token),
            timeout=timeout_s or config.http_timeout_s,
        )
        resp.raise_for_status()
        body: Any = resp.json()
    except Exception as e:
        bt.logging.debug(f"[openquantum] credits fetch failed: {e}")
        return None
    if not isinstance(body, dict):
        return None
    raw = body.get("full_credits")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def below_min_credits(config: OpenQuantumConfig) -> Tuple[Optional[bool], Optional[float]]:
    credits = get_remaining_credits(config)
    if credits is None:
        return None, None
    return credits < float(config.min_credits), credits


def should_rate_limit_for_low_credits(config: OpenQuantumConfig) -> Optional[bool]:
    is_below, _ = below_min_credits(config)
    return is_below
