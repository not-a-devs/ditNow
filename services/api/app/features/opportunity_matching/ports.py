"""Read ports for FR-OPP-002 matching. No production adapter exists in this package.

The opportunity source is the existing API-OPP `OpportunityCatalog` (same IDs, same approved
public projection); this module never stores or scrapes a second opportunity list.

`AcademicContextReader` is an authorized read of the verified actor's *current* academic
memberships. The shared auth/DB owner must resolve it at request time from the common
identity + approved `academic_memberships` ledger (department UUID -> catalog department code),
never from token claims, query/body values or a new profile table. Expired/pending memberships
must not be returned. It returns None when the actor is not a current active student context.

`RecruitmentReferenceReader` is an optional seam to the community recruitment aggregate
(FR-OPP-005). Recruitments are community data: the service asks for them only after the same
`require_member` check the community routes use, on a `CommunityActor` resolved fresh for this
request by the community auth owner and bound to the verified principal. Academic membership alone
never grants community access. The adapter receives that actor and must apply its own
actor-scoped visibility; it returns only recruitments linked to the given opportunity IDs that the
community recruitment listing would show this actor. The service projects them to id/title/field/
roles/deadline only; owner, body, applicants and counts never leave this module.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.features.community.domain import CommunityActor, Recruitment


@dataclass(frozen=True, slots=True)
class AcademicMembership:
    """One currently approved membership. `grade` None means year is not recorded."""

    department_code: str
    grade: int | None = None


@dataclass(frozen=True, slots=True)
class AcademicContext:
    user_id: UUID
    memberships: tuple[AcademicMembership, ...] = ()


class AcademicContextReader(Protocol):
    def current(self, user_id: UUID) -> AcademicContext | None: ...


class RecruitmentReferenceReader(Protocol):
    def linked_recruitments(
        self, actor: CommunityActor, opportunity_ids: Sequence[UUID], now: datetime
    ) -> Sequence[Recruitment]: ...
