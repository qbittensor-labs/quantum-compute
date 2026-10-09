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

"""Validator-local miner capability cache and ban helpers."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Dict, List

from qbittensor.constants import TIMESTAMP_FORMAT
from qbittensor.database.database_manager import DatabaseManager
from qbittensor.utils.time import timestamp, timestamp_str

CAPABILITIES_TTL_SECONDS = 600


def _parse_classes(raw: Any) -> List[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(c).strip() for c in raw if str(c).strip()]
    text = str(raw).strip()
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(c).strip() for c in data if str(c).strip()]
        except Exception:
            pass
    return [part.strip() for part in text.split(",") if part.strip()]


def upsert_capabilities(db: DatabaseManager, hotkey: str, classes: List[str]) -> None:
    """Store advertised backend_class.short_code values for a miner axon."""
    payload = json.dumps([str(c).strip() for c in classes if str(c).strip()])
    query = """
        INSERT OR REPLACE INTO miner_capabilities (hotkey, classes, updated_at)
        VALUES (?, ?, ?)
    """
    with db.lock:
        db.query_and_commit_with_values(query, (hotkey, payload, timestamp_str()))


def get_placeable_classes(
    db: DatabaseManager,
    ttl_seconds: int = CAPABILITIES_TTL_SECONDS,
) -> Dict[str, List[str]]:
    """Return hotkey -> non-empty class list, dropping stale cache rows."""
    cutoff = (timestamp() - timedelta(seconds=int(ttl_seconds))).strftime(TIMESTAMP_FORMAT)
    try:
        with db.lock:
            rows = db.query("SELECT hotkey, classes, updated_at FROM miner_capabilities")
    except Exception:
        return {}
    out: Dict[str, List[str]] = {}
    for row in rows or []:
        hotkey, raw_classes, updated_at = row[0], row[1], row[2]
        if not hotkey or not updated_at or str(updated_at) < cutoff:
            continue
        parsed = _parse_classes(raw_classes)
        if parsed:
            out[str(hotkey)] = parsed
    return out


def has_capability_record(
    db: DatabaseManager,
    hotkey: str,
    ttl_seconds: int = CAPABILITIES_TTL_SECONDS,
) -> bool:
    """Recent advertisement, including an empty class list. Stale rows do not count."""
    cutoff = (timestamp() - timedelta(seconds=int(ttl_seconds))).strftime(TIMESTAMP_FORMAT)
    try:
        with db.lock:
            row = db.query_one_with_values(
                "SELECT hotkey, updated_at FROM miner_capabilities WHERE hotkey=?",
                (hotkey,),
            )
    except Exception:
        return False
    if not row:
        return False
    updated_at = row[1] if len(row) > 1 else None
    if not updated_at or str(updated_at) < cutoff:
        return False
    return True


def is_banned(db: DatabaseManager, hotkey: str) -> bool:
    """True when miner_ban.banned_until is in the future."""
    try:
        with db.lock:
            row = db.query_one_with_values(
                "SELECT banned_until FROM miner_ban WHERE hotkey=?",
                (hotkey,),
            )
    except Exception:
        return False
    if not row or not row[0]:
        return False
    return str(row[0]) > timestamp_str()


PROOF_BAN_HOURS = 24.0
LEASE_BAN_HOURS = 24.0


def ban_miner(
    db: DatabaseManager,
    hotkey: str,
    reason: str,
    *,
    hours: float = PROOF_BAN_HOURS,
) -> None:
    """Record a local ban. Strikes increment on repeat."""
    until = (timestamp() + timedelta(hours=hours)).strftime(TIMESTAMP_FORMAT)
    strikes = 1
    try:
        with db.lock:
            existing = db.query_one_with_values(
                "SELECT strikes FROM miner_ban WHERE hotkey=?",
                (hotkey,),
            )
        if existing and existing[0]:
            try:
                strikes = int(existing[0]) + 1
            except (TypeError, ValueError):
                strikes = 1
    except Exception:
        strikes = 1
    query = """
        INSERT OR REPLACE INTO miner_ban (hotkey, reason, strikes, banned_until, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """
    with db.lock:
        db.query_and_commit_with_values(
            query,
            (hotkey, reason, strikes, until, timestamp_str()),
        )
