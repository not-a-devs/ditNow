"""Test-only in-memory fakes for API-OPP Protocols. Never a production persistence layer."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.features.opportunities.repository import (
    CheckRecord,
    OpportunityFile,
    OpportunityPage,
    OpportunityQuery,
    OpportunityRecord,
    SavedRecord,
    StatusEvent,
    TargetScope,
)
from app.features.opportunities.schemas import (
    OpportunityKind,
    PublicationStatus,
    SourceKind,
    SubmissionMode,
)
from app.features.opportunities.service import matches

NOW = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)
USER_A = UUID("00000000-0000-4000-8000-00000000000a")
USER_B = UUID("00000000-0000-4000-8000-00000000000b")


def make_opportunity(**overrides) -> OpportunityRecord:
    values = dict(
        id=uuid4(),
        kind=OpportunityKind.SCHOLARSHIP,
        title="[DEMO] 가상 외부 장학금",
        organization="가상 장학재단",
        eligibility="가상 시연 자격 조건",
        submission_mode=SubmissionMode.EXTERNAL_DOCUMENT_SUBMISSION,
        source_kind=SourceKind.DEMO,
        status=PublicationStatus.PUBLISHED,
        deadline_at=NOW + timedelta(days=7),
        destination="가상 재단 이메일 접수(시연)",
        original_url="https://example.test/demo-scholarship",
        files=(OpportunityFile("demo-form.hwp", "https://example.test/demo-form.hwp"),),
    )
    values.update(overrides)
    return OpportunityRecord(**values)


class FakeCatalog:
    def __init__(self, records: list[OpportunityRecord], *, leak_unfiltered: bool = False):
        self.records = {r.id: r for r in records}
        self.leak_unfiltered = leak_unfiltered

    def list_public(self, query: OpportunityQuery, now: datetime) -> OpportunityPage:
        items = list(self.records.values())
        if not self.leak_unfiltered:
            items = [r for r in items if matches(r, query, now)]
        start = int(query.cursor or 0)
        page = items[start : start + query.limit]
        more = start + query.limit < len(items)
        return OpportunityPage(page, str(start + query.limit) if more else None)

    def get(self, opportunity_id: UUID) -> OpportunityRecord | None:
        return self.records.get(opportunity_id)


class FakeStore:
    def __init__(self):
        self.saved: dict[tuple[UUID, UUID], SavedRecord] = {}
        self.checks: dict[UUID, CheckRecord] = {}
        self.keys: dict[tuple[UUID, str], tuple[UUID, str]] = {}
        self.events: list[StatusEvent] = []

    def get(self, user_id, opportunity_id):
        return self.saved.get((user_id, opportunity_id))

    def list_for_user(self, user_id):
        return [r for (uid, _), r in self.saved.items() if uid == user_id]

    def insert_if_absent(self, record):
        key = (record.user_id, record.opportunity_id)
        if key in self.saved:
            return self.saved[key], False
        self.saved[key] = record
        return record, True

    def compare_and_set(self, record, expected_revision):
        key = (record.user_id, record.opportunity_id)
        current = self.saved.get(key)
        if current is None or current.revision != expected_revision:
            return False
        self.saved[key] = record
        return True

    def delete_with_checks(self, user_id, saved_id, expected_revision):
        for key, row in list(self.saved.items()):
            if row.id == saved_id and row.user_id == user_id:
                if row.revision != expected_revision:
                    return False
                del self.saved[key]
                for cid in [c.id for c in self.checks.values() if c.saved_id == saved_id]:
                    del self.checks[cid]
                return True
        return False

    def append_status_event(self, event):
        self.events.append(event)

    def list_checks(self, saved_id):
        return [c for c in self.checks.values() if c.saved_id == saved_id]

    def find_check_by_idempotency_key(self, saved_id, key):
        hit = self.keys.get((saved_id, key))
        if hit is None or hit[0] not in self.checks:
            return None
        return self.checks[hit[0]], hit[1]

    def insert_check(self, record, idempotency_key, request_hash):
        self.checks[record.id] = record
        self.keys[(record.saved_id, idempotency_key)] = (record.id, request_hash)

    def compare_and_set_check(self, record, expected_revision):
        current = self.checks.get(record.id)
        if current is None or current.revision != expected_revision:
            return False
        self.checks[record.id] = record
        return True

    def delete_check(self, saved_id, check_id, expected_revision):
        current = self.checks.get(check_id)
        if current is None or current.saved_id != saved_id:
            return False
        if current.revision != expected_revision:
            return False
        del self.checks[check_id]
        return True

    def bump_revision_behind_service(self, user_id, opportunity_id):
        key = (user_id, opportunity_id)
        self.saved[key] = replace(self.saved[key], revision=self.saved[key].revision + 1)


DEPARTMENT_SCOPE = TargetScope(level="department", department_codes=("CSW",))
