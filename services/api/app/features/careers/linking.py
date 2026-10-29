"""FR-OPP-005 seam: which public contest opportunities a community recruitment may reference.

Implements community's `OpportunityVisibility` Protocol so root can inject it as
`CommunityDependencies(opportunities=...)`. It only answers "may this ID be referenced"; it
never reads or writes recruitments, and a link is an ID reference, not a team or entry record.
"""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from app.features.careers.domain import DemoCareerPolicy
from app.features.opportunities.repository import OpportunityCatalog, OpportunityRecord
from app.features.opportunities.schemas import OpportunityKind, PublicationStatus
from app.features.opportunities.service import deadline_passed
from app.schemas.common import utc_now


def contest_linkable(
    record: OpportunityRecord | None, policy: DemoCareerPolicy, now: datetime
) -> bool:
    if record is None or record.status is not PublicationStatus.PUBLISHED:
        return False
    if record.kind is not OpportunityKind.CONTEST:
        return False
    return policy.link_closed_contests or not deadline_passed(record, now)


class ContestTeamLinkVisibility:
    """Missing, hidden, non-contest and malformed IDs all return False (no probing)."""

    def __init__(
        self,
        catalog: OpportunityCatalog,
        policy: DemoCareerPolicy,
        *,
        clock: Callable[[], datetime] = utc_now,
    ):
        self._catalog = catalog
        self._policy = policy
        self._clock = clock

    def is_linkable(self, actor_id: str, opportunity_id: str) -> bool:
        # Contests are public; actor_id is accepted for the Protocol but grants nothing extra.
        del actor_id
        try:
            parsed = UUID(opportunity_id)
        except (ValueError, AttributeError, TypeError):
            return False
        return contest_linkable(self._catalog.get(parsed), self._policy, self._clock())
