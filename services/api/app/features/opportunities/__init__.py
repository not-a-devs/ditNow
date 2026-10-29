"""API-OPP feature package (FR-OPP-001 read, FR-OPP-003, FR-OPP-004).

Root integration: `include_router(create_router(OpportunityDependencies(...)), prefix="/api/v1")`.
The default `router` fails closed with 503 until auth and DB providers are injected.
"""

from app.features.opportunities.dependencies import OpportunityDependencies, Principal
from app.features.opportunities.repository import OpportunityCatalog, SavedOpportunityStore
from app.features.opportunities.router import create_router, router
from app.features.opportunities.service import OpportunityService

__all__ = [
    "OpportunityCatalog",
    "OpportunityDependencies",
    "OpportunityService",
    "Principal",
    "SavedOpportunityStore",
    "create_router",
    "router",
]
