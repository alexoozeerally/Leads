"""The ``BusinessProvider`` interface.

The rest of the app depends ONLY on this abstraction, never on a concrete
provider. Adding a provider = adding one subclass + registering it in the
factory. This is a hard architectural rule: nothing downstream may import a
concrete provider directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.business import Business, DiscoveryQuery


class BusinessProvider(ABC):
    """Abstract source of businesses.

    Implementations MUST document their data-source licence / ToS in a comment,
    normalise every record into :class:`Business`, and leave unknown fields
    ``None`` rather than inventing values.
    """

    #: Short registry key, e.g. ``"csv"`` or ``"osm"``.
    name: str = "base"

    @abstractmethod
    async def search(self, query: DiscoveryQuery) -> list[Business]:
        """Return businesses matching ``query`` as normalised :class:`Business`."""
        raise NotImplementedError
