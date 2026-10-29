"""Collaboration feature: anonymous comments/bookmarks/search/report requests (FR-COM-002/003),
virtual study/club groups (FR-COM-006) and group activity space (FR-COM-007).

``router`` fails closed (503) until the auth/DB owners inject providers via
``create_collaboration_router(CollaborationDependencies(...))``. Mounting is done by the root
owner. Operator report review, sanctions, user blocking and appeals are BLOCKED (no routes).
"""

from app.features.collaboration.domain import CollaborationActor, ParticipationGrant
from app.features.collaboration.ports import (
    CollaborationStore,
    CollaborationUnitOfWork,
    StoreConflict,
)
from app.features.collaboration.router import (
    CollaborationDependencies,
    create_collaboration_router,
    router,
)
from app.features.collaboration.service import CollaborationService

__all__ = [
    "CollaborationActor",
    "CollaborationDependencies",
    "CollaborationService",
    "CollaborationStore",
    "CollaborationUnitOfWork",
    "ParticipationGrant",
    "StoreConflict",
    "create_collaboration_router",
    "router",
]
