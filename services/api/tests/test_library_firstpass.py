import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.library.models import (
    BookingRecord,
    CatalogTitle,
    LibraryActor,
    LibraryPolicy,
    LoanRecord,
    MemberGrant,
    RevisionInput,
    Slot,
    WishInput,
    WishRecord,
)
from app.features.library.router import get_library_actor, get_library_service, router
from app.features.library.service import LibraryService
from app.schemas.common import ErrorCode

NOW = datetime(2026, 10, 30, tzinfo=UTC)
USER, OTHER = LibraryActor(user_id=uuid4()), LibraryActor(user_id=uuid4())
LOAN, OTHER_LOAN, SPACE = uuid4(), uuid4(), uuid4()
SLOT, OVERLAP = uuid4(), uuid4()
KEY = "test-key-123456789"


class FakeStore:
    """Test-only store. Locking here does not prove MariaDB transaction behavior."""

    def __init__(self):
        self.lock = RLock()
        self.grants = {
            actor.user_id: MemberGrant(active=True, eligible=True) for actor in (USER, OTHER)
        }
        self.policy = LibraryPolicy(
            name="테스트 가상 정책",
            renewal_days=7,
            max_renewals=1,
            allow_overdue_renewal=False,
            renewal_base="due_at",
            max_active_bookings=1,
        )
        self.titles = [
            CatalogTitle(id=uuid4(), title=f"가상 도서 {i}", author="가상 저자", available_copies=1)
            for i in range(3)
        ]
        self.loan_rows = {
            id: LoanRecord(
                id=id,
                owner_id=actor.user_id,
                title="가상 대출 도서",
                due_at=NOW + timedelta(days=1),
                state="active",
                renewal_count=0,
                renewable=True,
                revision=1,
            )
            for id, actor in [(LOAN, USER), (OTHER_LOAN, OTHER)]
        }
        self.slot_rows = {
            id: Slot(
                id=id,
                space_id=SPACE,
                space_name="가상 그룹실",
                starts_at=NOW + timedelta(hours=offset),
                ends_at=NOW + timedelta(hours=offset + 2),
                available=True,
                revision=1,
            )
            for id, offset in [(SLOT, 3), (OVERLAP, 4)]
        }
        self.wish_rows, self.booking_rows, self.keys = {}, {}, {}

    def search(self, query, offset, limit):
        return [row for row in self.titles if query in row.title][offset : offset + limit]

    def slots(self, limit):
        return list(self.slot_rows.values())[:limit]

    @contextmanager
    def transaction(self, user_id):
        with self.lock:
            yield FakeTransaction(self, user_id)


class FakeTransaction:
    def __init__(self, store, user_id):
        self.store, self.user_id = store, user_id
        self.grant = store.grants.get(user_id, MemberGrant(active=False, eligible=False))
        self.policy = store.policy

    def loans(self):
        return list(self.store.loan_rows.values())

    def wishes(self):
        return list(self.store.wish_rows.values())

    def bookings(self):
        return list(self.store.booking_rows.values())

    def loan(self, id):
        return self.store.loan_rows.get(id)

    def wish(self, id):
        return self.store.wish_rows.get(id)

    def booking(self, id):
        return self.store.booking_rows.get(id)

    def slot(self, id):
        return self.store.slot_rows.get(id)

    def replay(self, operation, key, digest):
        previous = self.store.keys.get((self.user_id, operation, key))
        if previous and previous[0] != digest:
            raise ApiError(ErrorCode.CONFLICT)
        return previous[1] if previous else None

    def remember(self, operation, key, digest, id):
        self.store.keys[self.user_id, operation, key] = digest, id

    def renew(self, id, revision, due_at, operation, key, digest):
        row = self.store.loan_rows[id]
        if row.revision != revision:
            raise ApiError(ErrorCode.CONFLICT)
        result = row.model_copy(
            update={
                "due_at": due_at,
                "renewal_count": row.renewal_count + 1,
                "revision": revision + 1,
            }
        )
        self.store.loan_rows[id] = result
        self.remember(operation, key, digest, id)
        return result

    def request_title(self, body, now, operation, key, digest):
        row = WishRecord(
            id=uuid4(),
            owner_id=self.user_id,
            **body.model_dump(),
            state="requested",
            created_at=now,
        )
        self.store.wish_rows[row.id] = row
        self.remember(operation, key, digest, row.id)
        return row

    def reserve(self, id, revision, now, operation, key, digest):
        slot = self.store.slot_rows[id]
        for row in self.store.booking_rows.values():
            booked_slot = self.store.slot_rows[row.slot_id]
            if (
                row.state == "reserved"
                and booked_slot.space_id == slot.space_id
                and row.starts_at < slot.ends_at
                and slot.starts_at < row.ends_at
            ):
                raise ApiError(ErrorCode.CONFLICT)
        if slot.revision != revision:
            raise ApiError(ErrorCode.CONFLICT)
        row = BookingRecord(
            id=uuid4(),
            owner_id=self.user_id,
            slot_id=id,
            space_name=slot.space_name,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
            state="reserved",
            revision=1,
        )
        self.store.booking_rows[row.id] = row
        self.store.slot_rows[id] = slot.model_copy(
            update={"available": False, "revision": revision + 1}
        )
        self.remember(operation, key, digest, row.id)
        return row

    def cancel(self, id, revision, now, operation, key, digest):
        row = self.store.booking_rows[id]
        if row.revision != revision:
            raise ApiError(ErrorCode.CONFLICT)
        changed = row.model_copy(update={"state": "cancelled", "revision": revision + 1})
        self.store.booking_rows[id] = changed
        slot = self.store.slot_rows[row.slot_id]
        self.store.slot_rows[row.slot_id] = slot.model_copy(
            update={"available": True, "revision": slot.revision + 1}
        )
        self.remember(operation, key, digest, id)
        return changed


@pytest.fixture
def setup():
    store = FakeStore()
    return store, LibraryService(store, clock=lambda: NOW)


def denied(code, call):
    with pytest.raises(ApiError) as exc:
        call()
    assert exc.value.code == code


def test_catalog_search_has_bounded_pages(setup):
    store, service = setup
    page = service.catalog("가상", 0, 2)
    assert len(page.items) == 2 and page.has_more
    assert len(service.catalog("가상", 2, 2).items) == 1
    assert service.catalog("찾을 수 없음", 0, 2).items == []


def test_missing_injected_policy_is_unavailable(setup):
    store, service = setup
    store.policy = None
    denied(ErrorCode.UNAVAILABLE, lambda: service.overview(USER))


def test_personal_projection_and_guessed_other_loan_denied(setup):
    store, service = setup
    own = service.overview(USER)
    assert [loan.id for loan in own.loans] == [LOAN]
    assert (
        "owner_id" not in own.model_dump_json() and str(USER.user_id) not in own.model_dump_json()
    )
    denied(
        ErrorCode.NOT_FOUND,
        lambda: service.renew(USER, OTHER_LOAN, RevisionInput(expected_revision=1), KEY),
    )


def test_renewal_policy_cas_idempotency_and_revocation(setup):
    store, service = setup
    body = RevisionInput(expected_revision=1)
    first = service.renew(USER, LOAN, body, KEY)
    assert first.due_at == NOW + timedelta(days=8) and first.renewal_count == 1
    assert service.renew(USER, LOAN, body, KEY) == first
    denied(
        ErrorCode.CONFLICT,
        lambda: service.renew(USER, LOAN, RevisionInput(expected_revision=2), KEY),
    )
    denied(
        ErrorCode.CONFLICT,
        lambda: service.renew(
            USER, LOAN, RevisionInput(expected_revision=2), "different-key-12345"
        ),
    )
    store.grants[USER.user_id] = MemberGrant(active=True, eligible=False)
    denied(ErrorCode.FORBIDDEN, lambda: service.renew(USER, LOAN, body, KEY))


@pytest.mark.parametrize("change", [{"state": "returned"}, {"renewable": False}, {"due_at": NOW}])
def test_renewal_unavailable_or_overdue_rejected(setup, change):
    store, service = setup
    store.loan_rows[LOAN] = store.loan_rows[LOAN].model_copy(update=change)
    denied(
        ErrorCode.CONFLICT,
        lambda: service.renew(USER, LOAN, RevisionInput(expected_revision=1), KEY),
    )


def test_policy_must_not_shorten_due_date(setup):
    store, service = setup
    store.policy = store.policy.model_copy(
        update={"renewal_base": "request_time", "renewal_days": 1}
    )
    denied(
        ErrorCode.CONFLICT,
        lambda: service.renew(USER, LOAN, RevisionInput(expected_revision=1), KEY),
    )


def test_wish_payload_idempotency_and_own_list(setup):
    store, service = setup
    body = WishInput(title="가상 희망 도서", author="가상 저자", reason="시연용 요청")
    first = service.request_title(USER, body, KEY)
    assert first.state == "requested" and service.request_title(USER, body, KEY).id == first.id
    assert len(store.wish_rows) == 1 and service.overview(OTHER).wishes == []
    denied(
        ErrorCode.CONFLICT,
        lambda: service.request_title(
            USER, WishInput(title="다른 제목", author="저자", reason=""), KEY
        ),
    )


def test_slot_overlap_across_distinct_slot_ids_and_ownership(setup):
    store, service = setup
    reserved = service.reserve(USER, SLOT, RevisionInput(expected_revision=1), KEY)
    assert service.reserve(USER, SLOT, RevisionInput(expected_revision=1), KEY).id == reserved.id
    denied(
        ErrorCode.CONFLICT,
        lambda: service.reserve(OTHER, OVERLAP, RevisionInput(expected_revision=1), KEY),
    )
    denied(
        ErrorCode.NOT_FOUND,
        lambda: service.cancel(OTHER, reserved.id, RevisionInput(expected_revision=1), KEY),
    )
    assert service.overview(OTHER).bookings == []
    cancelled = service.cancel(USER, reserved.id, RevisionInput(expected_revision=1), KEY)
    assert cancelled.state == "cancelled" and cancelled.revision == 2
    assert service.cancel(USER, reserved.id, RevisionInput(expected_revision=1), KEY) == cancelled


def test_two_actors_cannot_reserve_same_space_at_once(setup):
    store, service = setup

    def reserve(actor):
        try:
            service.reserve(actor, SLOT, RevisionInput(expected_revision=1), KEY)
            return "ok"
        except ApiError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, (USER, OTHER)))
    assert results.count("ok") == 1 and results.count(ErrorCode.CONFLICT) == 1
    assert len(store.booking_rows) == 1


def test_started_slot_revoked_user_and_aware_times(setup):
    store, service = setup
    store.slot_rows[SLOT] = store.slot_rows[SLOT].model_copy(update={"starts_at": NOW})
    denied(
        ErrorCode.CONFLICT,
        lambda: service.reserve(USER, SLOT, RevisionInput(expected_revision=1), KEY),
    )
    store.grants[USER.user_id] = MemberGrant(active=False, eligible=False)
    denied(ErrorCode.FORBIDDEN, lambda: service.overview(USER))
    with pytest.raises(ValidationError):
        Slot(
            id=uuid4(),
            space_id=SPACE,
            space_name="가상",
            starts_at="2026-10-30T10:00:00",
            ends_at="2026-10-30T11:00:00",
            available=True,
            revision=1,
        )
    with pytest.raises(ValidationError):
        WishInput(title="   ", author="가상", reason="")
    with pytest.raises(ValidationError):
        CatalogTitle(
            id=uuid4(),
            title="가상",
            author="가상",
            available_copies=1,
            public_reference_url="https://user:secret@example.test",
        )


def test_unconfigured_provider_is_503_and_not_cached():
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        for path in ["/api/v1/library/catalog", "/api/v1/library/me", "/api/v1/library/slots"]:
            response = client.get(path)
            assert (
                response.status_code == 503
                and response.headers["Cache-Control"] == "private, no-store"
            )


def test_http_projection_validation_cache_and_no_client_role(setup):
    store, service = setup
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_library_actor] = lambda: USER
    app.dependency_overrides[get_library_service] = lambda: service
    assert "LoanRecord" not in app.openapi()["components"]["schemas"]
    with TestClient(app) as client:
        response = client.get("/api/v1/library/me")
        assert (
            response.status_code == 200 and response.headers["Cache-Control"] == "private, no-store"
        )
        assert "owner_id" not in response.text and str(USER.user_id) not in response.text
        invalid = client.get("/api/v1/library/catalog?limit=51")
        assert (
            invalid.status_code == 400 and invalid.headers["Cache-Control"] == "private, no-store"
        )
        path = f"/api/v1/library/me/loans/{LOAN}/renew"
        assert client.post(path, json={"expected_revision": 1}).status_code == 400
        assert (
            client.post(
                path,
                json={"expected_revision": 1, "role": "librarian"},
                headers={"Idempotency-Key": KEY},
            ).status_code
            == 400
        )
        assert (
            client.post(
                path, json={"expected_revision": 1}, headers={"Idempotency-Key": KEY}
            ).status_code
            == 200
        )


def test_http_failure_redaction_cache_and_revoked_access(setup, caplog):
    store, service = setup
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_library_actor] = lambda: USER
    app.dependency_overrides[get_library_service] = lambda: service
    store.grants[USER.user_id] = MemberGrant(active=False, eligible=False)
    with TestClient(app) as client:
        denied_response = client.get("/api/v1/library/me")
        assert (
            denied_response.status_code == 403
            and denied_response.headers["Cache-Control"] == "private, no-store"
        )

    def broken_search(*args):
        raise RuntimeError("private-database-password")

    store.search = broken_search
    with caplog.at_level(logging.ERROR, logger="ditnow.api"), TestClient(app) as client:
        response = client.get("/api/v1/library/catalog")
    assert response.status_code == 500 and response.headers["Cache-Control"] == "private, no-store"
    assert "private-database-password" not in response.text
    assert "private-database-password" not in "\n".join(
        r.message for r in caplog.records if r.name == "ditnow.api"
    )
