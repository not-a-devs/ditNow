"""Injected virtual demo policy, kept separate from any school rule.

No numeric value in this module is a DIT regulation. A deployment must inject an approved
``DemoAcademicPolicy``; without one every policy-dependent flow returns 503. Official school
rules (registration periods, credit limits, eligibility, approval chains, attendance judgement)
are NOT_CONNECTED and must never be filled from these demo values.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.features.academics.models import PolicyView, RequestKind, WindowView

BLOCKED_FLOWS: tuple[str, ...] = (
    "OPERATIONAL_APPROVAL",
    "OFFICIAL_GRADE_CHANGE",
    "GRADUATION_JUDGEMENT",
    "CERTIFICATE_ISSUANCE",
    "TUITION_PAYMENT",
    "BLUETOOTH_IDENTITY_CHECK",
)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Policy times must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class DemoWindow:
    opens_at: datetime
    closes_at: datetime

    def __post_init__(self) -> None:
        opens, closes = _aware(self.opens_at), _aware(self.closes_at)
        if closes <= opens:
            raise ValueError("Window must close after it opens")
        object.__setattr__(self, "opens_at", opens)
        object.__setattr__(self, "closes_at", closes)

    def contains(self, now: datetime) -> bool:
        """Half-open [opens_at, closes_at): the closing instant is already closed."""
        return self.opens_at <= now < self.closes_at


@dataclass(frozen=True, slots=True)
class DemoAcademicPolicy:
    policy_id: str
    label: str
    max_credits_per_term: int
    check_in_window: timedelta
    check_in_attempt_limit: int
    registration_windows: Mapping[UUID, DemoWindow] = field(default_factory=dict)
    request_windows: Mapping[RequestKind, DemoWindow] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.policy_id or "DEMO" not in self.label.upper():
            raise ValueError("A demo policy must be labelled as DEMO")
        if self.max_credits_per_term < 1 or self.check_in_attempt_limit < 1:
            raise ValueError("Demo limits must be positive")
        if not timedelta(0) < self.check_in_window <= timedelta(hours=24):
            raise ValueError("Check-in window must be within one day")

    def view(self) -> PolicyView:
        return PolicyView(
            policy_id=self.policy_id,
            label=self.label,
            registration_windows={
                str(term): WindowView(opens_at=w.opens_at, closes_at=w.closes_at)
                for term, w in self.registration_windows.items()
            },
            request_windows={
                kind: WindowView(opens_at=w.opens_at, closes_at=w.closes_at)
                for kind, w in self.request_windows.items()
            },
            max_credits_per_term=self.max_credits_per_term,
            check_in_window_minutes=int(self.check_in_window.total_seconds() // 60),
            check_in_attempt_limit=self.check_in_attempt_limit,
            blocked=list(BLOCKED_FLOWS),
        )
