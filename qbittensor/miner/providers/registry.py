from __future__ import annotations

import os
from typing import Dict, Callable

from .base import ProviderAdapter
from .mock import MockProviderAdapter


_FACTORY: Dict[str, Callable[[], ProviderAdapter]] = {
    "mock": lambda: MockProviderAdapter(),
}


def get_adapter(name: str | None = None) -> ProviderAdapter:
    """Resolve a provider adapter by name (defaults to env PROVIDER=mock)."""
    provider = name or os.getenv("PROVIDER", "mock").lower()
    if provider not in _FACTORY:
        raise ValueError(f"Unknown provider adapter: {provider}")
    return _FACTORY[provider]()


