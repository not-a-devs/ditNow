"""Test-only in-memory fakes for the API-JOB Protocols. Never a production persistence layer.

`FakeUnitOfWork` serialises transactions with one lock and restores a snapshot on exception.
That simulates the documented contract; it is not evidence of MariaDB isolation behaviour.
"""

import copy
import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.features.careers.domain import (
    ApplicationStatus,
    CareerGrant,
    CareersActor,
    DemoCareerPolicy,
)
from app.features.careers.ports import (
    ApplicationRecord,
    ClaimScope,
    EmployerDraftRecord,
    IdempotencyClaim,
    ProfileRecord,
    ProgramRecord,
    StoreConflict,
)

NOW = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)
USER_A = UUID("00000000-0000-4000-8000-00000000000a")
USER_B = UUID("00000000-0000-4000-8000-00000000000b")
ALL_STUDENT = frozenset({CareerGrant.PROFILE_SELF, CareerGrant.PROGRAM_APPLY_SELF})


def demo_policy(**overrides) -> DemoCareerPolicy:
    values = dict(
        policy_id="demo-careers-20261030",
        max_active_applications_per_user=3,
        enforce_program_window=True,
        allow_cancel_after_window=False,
        link_closed_contests=False,
        max_employer_drafts_per_actor=5,
    )
    values.update(overrides)
    return DemoCareerPolicy(**values)


def actor(user: UUID = USER_A) -> CareersActor:
    return CareersActor(user_id=user)


def make_program(**overrides) -> ProgramRecord:
    values = dict(
        id=uuid4(),
        title="[DEMO] 가상 취업 역량 캠프",
        host="가상 진로지원팀",
        summary="시연용 가상 프로그램",
        official=False,
        published=True,
        capacity=2,
        apply_starts_at=NOW - timedelta(days=1),
        apply_ends_at=NOW + timedelta(days=7),
    )
    values.update(overrides)
    return ProgramRecord(**values)


class InjectedFailure(Exception):
    """Simulated failure inside the transaction (e.g. claim insert or audit write)."""


class FakeUnitOfWork:
    def __init__(self, programs: list[ProgramRecord] | None = None):
        self.lock = threading.Lock()
        self.grant_map: dict[UUID, frozenset[CareerGrant]] = {}
        self.claims: dict[ClaimScope, IdempotencyClaim] = {}
        self.profiles: dict[UUID, ProfileRecord] = {}
        self.programs: dict[UUID, ProgramRecord] = {p.id: p for p in programs or []}
        self.applications: dict[UUID, ApplicationRecord] = {}
        self.drafts: dict[UUID, EmployerDraftRecord] = {}
        self.fail_put_claim = False
        self.transactions = 0

    def grant(self, user: UUID, *grants: CareerGrant) -> None:
        self.grant_map[user] = frozenset(grants)

    _STATE = ("grant_map", "claims", "profiles", "programs", "applications", "drafts")

    @contextmanager
    def transaction(self):
        with self.lock:
            self.transactions += 1
            snapshot = {name: copy.copy(getattr(self, name)) for name in self._STATE}
            try:
                yield FakeTransaction(self)
            except BaseException:
                for name, value in snapshot.items():
                    setattr(self, name, value)
                raise


class FakeTransaction:
    def __init__(self, uow: FakeUnitOfWork):
        self.u = uow

    def grants(self, user_id):
        return self.u.grant_map.get(user_id, frozenset())

    def find_claim(self, scope):
        return self.u.claims.get(scope)

    def put_claim(self, claim):
        if self.u.fail_put_claim:
            raise InjectedFailure()
        if claim.scope in self.u.claims:
            raise StoreConflict()
        self.u.claims[claim.scope] = claim

    # profiles
    def get_profile(self, user_id):
        return next((p for p in self.u.profiles.values() if p.user_id == user_id), None)

    def get_profile_by_id(self, profile_id):
        return self.u.profiles.get(profile_id)

    def insert_profile(self, record):
        if self.get_profile(record.user_id) is not None:
            raise StoreConflict()
        self.u.profiles[record.id] = record

    def update_profile(self, record, expected_revision):
        current = self.u.profiles.get(record.id)
        if current is None or current.revision != expected_revision:
            return False
        self.u.profiles[record.id] = record
        return True

    def delete_profile(self, user_id, profile_id, expected_revision):
        current = self.u.profiles.get(profile_id)
        if current is None or current.user_id != user_id or current.revision != expected_revision:
            return False
        del self.u.profiles[profile_id]  # claims are kept as tombstones
        return True

    # programs
    def list_programs(self):
        return list(self.u.programs.values())

    def get_program(self, program_id):
        return self.u.programs.get(program_id)

    def lock_program(self, program_id):
        return self.u.programs.get(program_id)  # the global lock already serialises

    def _active(self):
        return [a for a in self.u.applications.values() if a.status is ApplicationStatus.APPLIED]

    def count_active_for_program(self, program_id):
        return sum(1 for a in self._active() if a.program_id == program_id)

    def count_active_for_user(self, user_id):
        return sum(1 for a in self._active() if a.user_id == user_id)

    def find_active_application(self, user_id, program_id):
        return next(
            (a for a in self._active() if a.user_id == user_id and a.program_id == program_id),
            None,
        )

    def get_application(self, application_id):
        return self.u.applications.get(application_id)

    def list_applications(self, user_id):
        return [a for a in self.u.applications.values() if a.user_id == user_id]

    def insert_application(self, record):
        if self.find_active_application(record.user_id, record.program_id) is not None:
            raise StoreConflict()
        self.u.applications[record.id] = record

    def update_application(self, record, expected_revision):
        current = self.u.applications.get(record.id)
        if current is None or current.revision != expected_revision:
            return False
        self.u.applications[record.id] = record
        return True

    # employer drafts
    def list_employer_drafts(self, owner_id):
        return [d for d in self.u.drafts.values() if d.owner_id == owner_id]

    def get_employer_draft(self, draft_id):
        return self.u.drafts.get(draft_id)

    def insert_employer_draft(self, record):
        self.u.drafts[record.id] = record

    def update_employer_draft(self, record, expected_revision):
        current = self.u.drafts.get(record.id)
        if current is None or current.revision != expected_revision:
            return False
        self.u.drafts[record.id] = record
        return True

    def delete_employer_draft(self, owner_id, draft_id, expected_revision):
        current = self.u.drafts.get(draft_id)
        if current is None or current.owner_id != owner_id or current.revision != expected_revision:
            return False
        del self.u.drafts[draft_id]
        return True


def bump_revision(uow: FakeUnitOfWork, profile_id: UUID) -> None:
    """Simulate a concurrent writer changing the row between read and CAS."""
    current = uow.profiles[profile_id]
    uow.profiles[profile_id] = replace(current, revision=current.revision + 1)
