"""FR-OPP-002 personalized opportunity discovery + rule-based FR-AI-002/003 subset.

Root integration: `include_router(create_router(MatchingDependencies(...)), prefix="/api/v1")`.
The default `router` fails closed with 503 until auth, academic context and catalog are injected.
"""

from app.features.opportunity_matching.ports import (
    AcademicContext,
    AcademicContextReader,
    AcademicMembership,
    RecruitmentReferenceReader,
)
from app.features.opportunity_matching.router import MatchingDependencies, create_router, router
from app.features.opportunity_matching.service import MatchingService

__all__ = [
    "AcademicContext",
    "AcademicContextReader",
    "AcademicMembership",
    "MatchingDependencies",
    "MatchingService",
    "RecruitmentReferenceReader",
    "create_router",
    "router",
]
