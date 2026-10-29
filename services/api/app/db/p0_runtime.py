"""Async transaction boundary around existing synchronous domain services and SQL adapters.

AsyncSession.run_sync bridges SQLAlchemy calls to aiomysql without blocking the event loop.
This module never opens an engine, reads credentials, installs routes, creates schema, or seeds.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import VerifiedPrincipal
from app.core.errors import ApiError
from app.features.community.domain import CommunityActor
from app.features.community.service import AnonymousPostService, RecruitmentService
from app.features.opportunities.repository import StoreConflict
from app.features.opportunities.service import OpportunityService
from app.repositories.community_sql import SQLAnonymousPosts, SQLPublicProfiles, SQLRecruitments
from app.repositories.opportunities_sql import SQLOpportunityCatalog, SQLSavedOpportunities
from app.repositories.p0_access import CurrentP0Access
from app.schemas.common import ErrorCode, utc_now

T = TypeVar("T")


@dataclass(frozen=True)
class P0Services:
    actor: CommunityActor
    posts: AnonymousPostService
    recruitments: RecruitmentService
    opportunities: OpportunityService


class P0Executor:
    def __init__(
        self,
        engine: AsyncEngine,
        clock: Callable[[], datetime] = utc_now,
        *,
        verify_principal: Callable[[AsyncSession, VerifiedPrincipal], Awaitable[None]]
        | None = None,
    ):
        self.sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        self.clock = clock
        self.verify_principal = verify_principal

    async def run(self, principal: VerifiedPrincipal, operation: Callable[[P0Services], T]) -> T:
        if not principal.active:
            raise ApiError(ErrorCode.UNAUTHORIZED)

        def invoke(session):
            access = CurrentP0Access(session, principal.user_id, self.clock)
            access.require(student=True)
            catalog = SQLOpportunityCatalog(session)
            return operation(
                P0Services(
                    actor=CommunityActor(str(principal.user_id), True),
                    posts=AnonymousPostService(
                        SQLAnonymousPosts(session, access), clock=self.clock
                    ),
                    recruitments=RecruitmentService(
                        SQLRecruitments(session, access),
                        SQLPublicProfiles(session, access),
                        opportunities=catalog,
                        clock=self.clock,
                    ),
                    opportunities=OpportunityService(
                        catalog, SQLSavedOpportunities(session, access), clock=self.clock
                    ),
                )
            )

        try:
            async with self.sessions() as session, session.begin():
                if self.verify_principal is not None:
                    await self.verify_principal(session, principal)
                return await session.run_sync(invoke)
        except SQLAlchemyError:
            raise ApiError(ErrorCode.UNAVAILABLE) from None
        except StoreConflict:
            raise ApiError(ErrorCode.CONFLICT) from None

    async def run_personal(
        self, principal: VerifiedPrincipal, operation: Callable[[OpportunityService], T]
    ) -> T:
        if not principal.active:
            raise ApiError(ErrorCode.UNAUTHORIZED)

        def invoke(session):
            access = CurrentP0Access(session, principal.user_id, self.clock)
            access.require()
            return operation(
                OpportunityService(
                    SQLOpportunityCatalog(session),
                    SQLSavedOpportunities(session, access),
                    clock=self.clock,
                )
            )

        try:
            async with self.sessions() as session, session.begin():
                if self.verify_principal is not None:
                    await self.verify_principal(session, principal)
                return await session.run_sync(invoke)
        except SQLAlchemyError:
            raise ApiError(ErrorCode.UNAVAILABLE) from None
        except StoreConflict:
            raise ApiError(ErrorCode.CONFLICT) from None

    async def public_opportunities(self, operation: Callable[[OpportunityService], T]) -> T:
        try:
            async with self.sessions() as session, session.begin():
                return await session.run_sync(
                    lambda sync: operation(
                        OpportunityService(SQLOpportunityCatalog(sync), clock=self.clock)
                    )
                )
        except SQLAlchemyError:
            raise ApiError(ErrorCode.UNAVAILABLE) from None
