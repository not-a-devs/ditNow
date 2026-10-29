"""API-JOB first pass (FR-JOB-001~004, FR-OPP-005~006 safe demo scope). Not mounted.

Root integration after auth/DB approval:
`include_router(create_careers_router(CareersDependencies(...)), prefix="/api/v1")`.
The default `router` fails closed with 503.
"""

from app.features.careers.domain import CareerGrant, CareersActor, DemoCareerPolicy
from app.features.careers.linking import ContestTeamLinkVisibility
from app.features.careers.ports import CareersTransaction, CareersUnitOfWork
from app.features.careers.router import CareersDependencies, create_careers_router, router
from app.features.careers.service import CareersService

__all__ = [
    "CareerGrant",
    "CareersActor",
    "CareersDependencies",
    "CareersService",
    "CareersTransaction",
    "CareersUnitOfWork",
    "ContestTeamLinkVisibility",
    "DemoCareerPolicy",
    "create_careers_router",
    "router",
]
