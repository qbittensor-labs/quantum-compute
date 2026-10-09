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

"""Load a local `.env` and resolve Open Quantum API base URLs.

Process environment wins over the file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

DEFAULT_JOB_API_URL = "https://jobs.openquantum.com"
DEFAULT_TENSORAUTH_URL = "https://tensorauth.openquantum.com"
DEFAULT_TELEMETRY_API_URL = "https://telemetry.openquantum.com"
DEFAULT_CA_BASE_URL = "https://ca.openquantum.com"

_ENV_LOADED = False


def load_env(*, override: bool = False, force: bool = False) -> bool:
    """
    Load a local `.env` into the process environment (once by default).

    Search order (first existing file wins unless *force* reloads):
    1. ``ENV_FILE`` or ``DOTENV_PATH`` if set
    2. ``find_dotenv(usecwd=True)`` (walks up from the current working directory)
    3. Repo root next to the installed/packaged ``qbittensor`` tree

    Returns True if a file was found and passed to ``load_dotenv``.
    """
    global _ENV_LOADED
    if _ENV_LOADED and not force:
        return True

    candidates: list[Path] = []
    explicit = os.getenv("ENV_FILE") or os.getenv("DOTENV_PATH")
    if explicit:
        candidates.append(Path(explicit).expanduser())

    found = find_dotenv(usecwd=True)
    if found:
        candidates.append(Path(found))

    # parents[2] is the checkout root. A quantum-compute submodule also reads the parent .env.
    try:
        pkg_root = Path(__file__).resolve().parents[2]
        candidates.append(pkg_root / ".env")
        if pkg_root.name == "quantum-compute":
            candidates.append(pkg_root.parent / ".env")
    except Exception:
        pass

    candidates.append(Path.cwd() / ".env")

    loaded = False
    seen: set[str] = set()
    for path in candidates:
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            load_dotenv(dotenv_path=path, override=override)
            loaded = True
            # Later files only fill keys that are still unset.

    if not loaded:
        # Mark loaded even when no file exists.
        load_dotenv(override=override)

    _ENV_LOADED = True
    return loaded


@dataclass(frozen=True)
class ApiConfig:
    """Resolved API base URLs for Open Quantum services."""

    job_api_url: str
    tensorauth_url: str
    telemetry_api_url: str
    ca_base_url: str
    api_version: str


def get_api_config() -> ApiConfig:
    """Open Quantum API base URLs, with defaults where a value is unset."""
    load_env()

    job_api_url = os.getenv("JOB_API_URL") or os.getenv("JOB_SERVER_URL") or DEFAULT_JOB_API_URL
    tensorauth_url = os.getenv("TENSORAUTH_URL") or DEFAULT_TENSORAUTH_URL
    telemetry_api_url = os.getenv("METRICS_API_URL") or DEFAULT_TELEMETRY_API_URL
    ca_base_url = os.getenv("CA_BASE_URL") or DEFAULT_CA_BASE_URL
    api_version = os.getenv("API_VERSION", "1")

    return ApiConfig(
        job_api_url=job_api_url,
        tensorauth_url=tensorauth_url,
        telemetry_api_url=telemetry_api_url,
        ca_base_url=ca_base_url,
        api_version=api_version,
    )


def env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean env flag. Unset uses *default*; flags default OFF."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def env_csv(name: str, default: str = "") -> list[str]:
    """Parse a comma-separated env list, dropping empty tokens."""
    raw = os.getenv(name)
    if raw is None:
        raw = default
    return [part.strip() for part in raw.split(",") if part.strip()]


def resolve_netuid(netuid: int | None = None) -> int:
    """Prefer an explicit netuid, then ``NETUID`` env, then subnet constant 48."""
    if netuid is not None:
        return int(netuid)
    raw = os.getenv("NETUID")
    if raw is not None and raw.strip():
        try:
            return int(raw.strip())
        except ValueError:
            pass
    from qbittensor.constants import NETUID
    return int(NETUID)
