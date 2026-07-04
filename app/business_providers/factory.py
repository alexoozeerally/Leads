"""Provider factory / registry.

Concrete providers register themselves here; the app resolves the active provider
by name from configuration. This is the single seam through which providers enter
the system — nothing else should instantiate a concrete provider.
"""

from __future__ import annotations

from collections.abc import Callable

from app.business_providers.base import BusinessProvider
from app.config.settings import Settings, get_settings
from app.exceptions import ProviderError

_REGISTRY: dict[str, Callable[[Settings], BusinessProvider]] = {}


def register_provider(name: str, factory: Callable[[Settings], BusinessProvider]) -> None:
    """Register a provider constructor under ``name``."""
    _REGISTRY[name.lower()] = factory


def available_providers() -> list[str]:
    return sorted(_REGISTRY)


def get_provider(name: str | None = None, settings: Settings | None = None) -> BusinessProvider:
    """Resolve a provider by name (defaults to the configured provider)."""
    settings = settings or get_settings()
    key = (name or settings.business_provider).lower()
    if key not in _REGISTRY:
        raise ProviderError(
            f"Unknown business provider '{key}'. Available: {available_providers()}"
        )
    return _REGISTRY[key](settings)


def _register_builtins() -> None:
    """Import + register built-in providers.

    Guarded so the contracts layer imports cleanly even before the concrete
    providers exist (they arrive in Phase 1). Any provider that is present is
    registered; absent ones are simply skipped until added.
    """
    try:
        from app.business_providers.csv_provider import CSVBusinessProvider

        register_provider("csv", lambda s: CSVBusinessProvider(s.csv_provider_path, source="csv"))
    except ImportError:
        pass

    try:
        from app.business_providers.osm_provider import OSMBusinessProvider

        register_provider(
            "osm",
            lambda s: OSMBusinessProvider(
                s.overpass_url,
                nominatim_url=s.nominatim_url,
                user_agent=s.crawler_user_agent,
            ),
        )
    except ImportError:
        pass


_register_builtins()
