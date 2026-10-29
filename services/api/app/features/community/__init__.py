"""Community feature: anonymous free board (FR-COM-001) and real-name recruitment (FR-COM-004).

``router`` fails closed (503) until the auth/DB owners inject providers via
``create_community_router(CommunityDependencies(...))``. Mounting is done by the root owner.
"""

from app.features.community.domain import CommunityActor
from app.features.community.idempotency import IdempotencyClaim
from app.features.community.repository import (
    AnonymousPostRepository,
    OpportunityVisibility,
    PublicProfileReader,
    RecruitmentRepository,
)
from app.features.community.router import (
    CommunityDependencies,
    create_community_router,
    router,
)
from app.features.community.service import AnonymousPostService, RecruitmentService

__all__ = [
    "AnonymousPostRepository",
    "AnonymousPostService",
    "CommunityActor",
    "CommunityDependencies",
    "IdempotencyClaim",
    "OpportunityVisibility",
    "PublicProfileReader",
    "RecruitmentRepository",
    "RecruitmentService",
    "create_community_router",
    "router",
]
