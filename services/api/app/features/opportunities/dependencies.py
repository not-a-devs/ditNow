"""Injection points for API-OPP. Defaults fail closed until root wires real auth and DB.

BLOCKED: the shared auth dependency (OPEN-002/003) and platform DB adapter are owned by other
tasks. Until they are injected, every protected or repository-backed route returns 503.
"""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from app.core.errors import ApiError
from app.features.opportunities.repository import OpportunityCatalog, SavedOpportunityStore
from app.schemas.common import ErrorCode


@dataclass(frozen=True)
class Principal:
    """Verified internal user id produced by the shared auth dependency, never by the client."""

    user_id: UUID


def auth_not_configured() -> Principal:
    raise ApiError(ErrorCode.UNAVAILABLE)


def catalog_not_configured() -> OpportunityCatalog:
    raise ApiError(ErrorCode.UNAVAILABLE)


def store_not_configured() -> SavedOpportunityStore:
    raise ApiError(ErrorCode.UNAVAILABLE)


@dataclass(frozen=True)
class OpportunityDependencies:
    """FastAPI dependency callables. Root replaces these with real providers."""

    current_principal: Callable[..., Principal] = auth_not_configured
    catalog: Callable[..., OpportunityCatalog] = catalog_not_configured
    store: Callable[..., SavedOpportunityStore] = store_not_configured
