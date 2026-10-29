"""Test-only fakes for FR-OPP-002 matching ports. Never a production provider or DB adapter.

The opportunity catalog fake and record factory are reused from the API-OPP test support so both
features exercise the same catalog contract and IDs.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from test_opportunities_support import NOW, USER_A, USER_B, FakeCatalog, make_opportunity

from app.features.community.domain import Recruitment, RecruitmentStatus
from app.features.opportunities.repository import OpportunityPage, OpportunityQuery
from app.features.opportunity_matching.ports import AcademicContext, AcademicMembership
from app.features.opportunity_matching.service import MatchingService

__all__ = [
    "NOW",
    "USER_A",
    "USER_B",
    "FakeCatalog",
    "make_opportunity",
]

USER_C = UUID("00000000-0000-4000-8000-00000000000c")
OWNER_SECRET = "owner-private-0001"
BODY_SECRET = "recruitment private body text"

CONTEXTS = {
    USER_A: AcademicContext(USER_A, (AcademicMembership("CSE", 2),)),
    USER_B: AcademicContext(USER_B, (AcademicMembership("EE", 3),)),
}


@dataclass
class FakeContexts:
    table: dict[UUID, AcademicContext | None] = field(default_factory=lambda: dict(CONTEXTS))
    calls: list[UUID] = field(default_factory=list)

    def current(self, user_id: UUID) -> AcademicContext | None:
        self.calls.append(user_id)
        return self.table.get(user_id)


@dataclass
class FakeRecruitments:
    rows: list[Recruitment] = field(default_factory=list)
    fail: bool = False
    calls: list[list[UUID]] = field(default_factory=list)

    def linked_recruitments(self, opportunity_ids: Sequence[UUID], now: datetime):
        self.calls.append(list(opportunity_ids))
        if self.fail:
            raise RuntimeError("adapter detail that must not leak")
        wanted = {str(oid) for oid in opportunity_ids}
        return [r for r in self.rows if r.opportunity_id in wanted]


def make_recruitment(opportunity_id: UUID, **overrides) -> Recruitment:
    values = dict(
        id="rec-0001",
        owner_id=OWNER_SECRET,
        title="[DEMO] 가상 공모전 팀원 모집",
        body=BODY_SECRET,
        field="AI",
        roles=("백엔드", "디자인"),
        capacity=4,
        accepted_count=1,
        deadline_at=NOW + timedelta(days=3),
        status=RecruitmentStatus.OPEN,
        opportunity_id=str(opportunity_id),
        revision=1,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
    )
    values.update(overrides)
    return Recruitment(**values)


class LoopingCatalog:
    """Misbehaving adapter that keeps returning the same cursor."""

    def __init__(self, records):
        self.records = records

    def list_public(self, query: OpportunityQuery, now: datetime) -> OpportunityPage:
        return OpportunityPage(self.records[:2], "same")

    def get(self, opportunity_id):
        return None


class OversizedCatalog(LoopingCatalog):
    """Adapter that ignores the requested page size."""

    def list_public(self, query: OpportunityQuery, now: datetime) -> OpportunityPage:
        return OpportunityPage(self.records, None)


def service(catalog, contexts=None, recruitments=None, now=NOW) -> MatchingService:
    return MatchingService(catalog, contexts or FakeContexts(), recruitments, clock=lambda: now)
