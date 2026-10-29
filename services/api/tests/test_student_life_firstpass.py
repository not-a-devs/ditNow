"""Dorm/help/badge safe subset: isolated fake, no student records or real DB."""

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
from app.features.student_life.models import (
    CancelInput,
    ChangeInput,
    CreateInput,
    DemoBadgeRecord,
    DemoLifePolicy,
    LifeActor,
    LifeGrant,
    LifeRequestRecord,
    PublicLifeGuide,
)
from app.features.student_life.router import get_life_actor, get_life_service, router
from app.features.student_life.service import StudentLifeService
from app.schemas.common import ErrorCode

NOW = datetime(2026, 10, 30, tzinfo=UTC)
A, B = LifeActor(user_id=uuid4()), LifeActor(user_id=uuid4())
DORM, INQUIRY, VOLUNTEER = uuid4(), uuid4(), uuid4()
KEY = "life-intent-key-12345"


class Store:
    """Test-only serial transaction fake, not proof of MariaDB isolation or GRANTs."""

    def __init__(self):
        self.lock = RLock()
        self.rows, self.keys, self.badge_rows, self.guide_rows = {}, {}, [], []
        self.policies = {
            id: DemoLifePolicy(
                program_id=id,
                kind=kind,
                name="테스트 가상 정책",
                revision=1,
                allowed_choices=choices,
                opens_at=NOW - timedelta(days=1),
                closes_at=NOW + timedelta(days=1),
                cancel_until=NOW + timedelta(days=2),
                max_per_user=1,
                capacity=1,
            )
            for id, kind, choices in [
                (DORM, "dorm", ["demo_dorm_a", "demo_dorm_b"]),
                (INQUIRY, "inquiry", ["process_information", "facility_information"]),
                (VOLUNTEER, "volunteer", ["demo_volunteer_a", "demo_volunteer_b"]),
            ]
        }
        self.grants = {
            a.user_id: LifeGrant(active=True, program_ids=set(self.policies)) for a in (A, B)
        }
        self.fail_event = False

    def guides(self, offset, limit):
        return self.guide_rows[offset : offset + limit]

    @contextmanager
    def transaction(self, user):
        with self.lock:
            rows, keys = dict(self.rows), dict(self.keys)
            try:
                yield Transaction(self, user)
            except BaseException:
                self.rows, self.keys = rows, keys
                raise


class Transaction:
    def __init__(self, store, user):
        self.s, self.user = store, user
        self.grant = store.grants.get(user, LifeGrant(active=False, program_ids=[]))

    def policies(self):
        return None if self.s.policies is None else list(self.s.policies.values())

    def policy(self, id):
        return self.s.policies.get(id)

    def requests(self):
        return list(self.s.rows.values())

    def program_count(self, id):
        return sum(r.program_id == id and r.state != "cancelled" for r in self.s.rows.values())

    def badges(self):
        return self.s.badge_rows

    def get(self, id):
        return self.s.rows.get(id)

    def replay(self, op, key, digest):
        old = self.s.keys.get((self.user, op, key))
        if old and old[0] != digest:
            raise ApiError(ErrorCode.CONFLICT)
        return old[1] if old else None

    def remember(self, row, op, key, digest):
        self.s.rows[row.id] = row
        if self.s.fail_event:
            raise RuntimeError("fictional-private-db-detail")
        self.s.keys[self.user, op, key] = digest, row.id
        return row

    def create(self, row, op, key, digest):
        assert row.owner_id == self.user
        return self.remember(row, op, key, digest)

    def replace(self, row, expected, op, key, digest):
        old = self.s.rows[row.id]
        if (
            old.owner_id != self.user
            or old.program_id != row.program_id
            or old.revision != expected
        ):
            raise ApiError(ErrorCode.CONFLICT)
        return self.remember(row, op, key, digest)


@pytest.fixture
def setup():
    s = Store()
    return s, StudentLifeService(s, clock=lambda: NOW)


def create_body(**updates):
    return CreateInput(
        **({"program_id": DORM, "choice": "demo_dorm_a", "expected_policy_revision": 1} | updates)
    )


def denied(code, callback):
    with pytest.raises(ApiError) as error:
        callback()
    assert error.value.code == code


def test_public_guides_are_empty_until_registered(setup):
    s, service = setup
    assert service.guides(0, 20).items == []
    s.guide_rows = [
        PublicLifeGuide(
            id=uuid4(),
            category="protected_help",
            title="미확인 공개 안내",
            summary="기관 안내를 추측하지 않음",
            revision=1,
        )
    ]
    guide = service.guides(0, 20).items[0]
    assert guide.source_kind == "UNKNOWN" and guide.source_url is None


@pytest.mark.parametrize(
    "updates",
    [
        {"source_kind": "OFFICIAL_PUBLIC"},
        {"source_kind": "OFFICIAL_PUBLIC", "source_url": "javascript:alert(1)", "checked_at": NOW},
        {
            "source_kind": "OFFICIAL_PUBLIC",
            "source_url": "https://u:pass@www.dit.ac.kr/kr/",
            "checked_at": NOW,
        },
        {
            "source_kind": "OFFICIAL_PUBLIC",
            "source_url": "https://evil.example/",
            "checked_at": NOW,
        },
        {"source_kind": "DEMO", "source_url": "https://www.dit.ac.kr/kr/", "checked_at": NOW},
    ],
)
def test_unverified_or_unsafe_source_cannot_be_official(updates):
    with pytest.raises(ValidationError):
        PublicLifeGuide(
            id=uuid4(), category="dorm", title="가상", summary="가상", revision=1, **updates
        )


@pytest.mark.parametrize(
    "program,choice",
    [(DORM, "demo_dorm_a"), (INQUIRY, "process_information"), (VOLUNTEER, "demo_volunteer_a")],
)
def test_create_modify_and_cancel_are_own_demo_records(setup, program, choice):
    s, service = setup
    body = create_body(program_id=program, choice=choice)
    row = service.create(A, body, KEY)
    assert row.state == "requested" and row.official_effect is False
    updated = service.change(
        A, row.id, ChangeInput(choice=choice, expected_revision=1, expected_policy_revision=1), KEY
    )
    assert updated.revision == 2
    result = service.change(
        A, row.id, CancelInput(expected_revision=2, expected_policy_revision=1), KEY, True
    )
    assert (result.state, result.revision) == ("cancelled", 3)
    assert "owner_id" not in result.model_dump()


def test_badges_and_answers_are_read_only_fictional_projections(setup):
    s, service = setup
    for owner in (A, B):
        s.badge_rows.append(
            DemoBadgeRecord(
                id=uuid4(),
                owner_id=owner.user_id,
                title="가상 참여 확인",
                state="DEMO_ISSUED",
                recorded_at=NOW,
            )
        )
    request = service.create(A, create_body(program_id=INQUIRY, choice="process_information"), KEY)
    s.rows[request.id] = s.rows[request.id].model_copy(
        update={"state": "answered", "answer_code": "demo_information_referred"}
    )
    result = service.overview(A)
    assert len(result.badges) == 1 and result.badges[0].verification == "NOT_OFFICIALLY_VERIFIABLE"
    assert result.sensitive_support == "BLOCKED" and result.requests[0].state == "answered"
    assert "owner_id" not in result.model_dump_json()
    with pytest.raises(ValidationError):
        DemoBadgeRecord(
            id=uuid4(),
            owner_id=A.user_id,
            title="가상 참여 확인",
            state="DEMO_ISSUED",
            recorded_at=NOW,
            official_effect=True,
        )


def test_other_user_parent_and_revoked_permissions_deny_reads_and_cancel(setup):
    s, service = setup
    row = service.create(A, create_body(), KEY)
    assert service.overview(B).requests == []
    cancel = CancelInput(expected_revision=1, expected_policy_revision=1)
    denied(ErrorCode.NOT_FOUND, lambda: service.change(B, row.id, cancel, KEY, True))
    s.grants[A.user_id] = LifeGrant(active=True, program_ids={INQUIRY})
    denied(ErrorCode.NOT_FOUND, lambda: service.change(A, row.id, cancel, KEY, True))
    s.grants[A.user_id] = LifeGrant(active=False, program_ids={DORM})
    denied(ErrorCode.FORBIDDEN, lambda: service.change(A, row.id, cancel, KEY, True))
    denied(ErrorCode.FORBIDDEN, lambda: service.create(A, create_body(), KEY))


def test_replay_scope_payload_cas_and_tombstone(setup):
    s, service = setup
    row = service.create(A, create_body(), KEY)
    assert service.create(A, create_body(), KEY).id == row.id
    denied(ErrorCode.CONFLICT, lambda: service.create(A, create_body(choice="demo_dorm_b"), KEY))
    changed = service.change(
        A,
        row.id,
        ChangeInput(choice="demo_dorm_b", expected_revision=1, expected_policy_revision=1),
        KEY,
    )
    denied(
        ErrorCode.CONFLICT,
        lambda: service.change(
            A, row.id, CancelInput(expected_revision=1, expected_policy_revision=1), KEY, True
        ),
    )
    cancelled = service.change(
        A,
        row.id,
        CancelInput(expected_revision=changed.revision, expected_policy_revision=1),
        KEY,
        True,
    )
    assert service.create(A, create_body(), KEY).state == "cancelled"
    del s.rows[row.id]
    denied(ErrorCode.NOT_FOUND, lambda: service.create(A, create_body(), KEY))
    assert cancelled.official_effect is False and not s.rows


def test_missing_policy_version_window_choice_and_limits(setup):
    s, service = setup
    denied(
        ErrorCode.CONFLICT, lambda: service.create(A, create_body(expected_policy_revision=2), KEY)
    )
    denied(
        ErrorCode.VALIDATION,
        lambda: service.create(A, create_body(choice="process_information"), KEY),
    )
    expired = StudentLifeService(s, clock=lambda: NOW + timedelta(days=1))
    denied(ErrorCode.CONFLICT, lambda: expired.create(A, create_body(), KEY))
    s.policies = None
    denied(ErrorCode.UNAVAILABLE, lambda: service.overview(A))
    denied(ErrorCode.UNAVAILABLE, lambda: service.create(A, create_body(), KEY))


def test_two_actors_cannot_claim_one_fictional_program_capacity(setup):
    s, service = setup

    def attempt(actor):
        try:
            return service.create(actor, create_body(), KEY).id
        except ApiError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, [A, B]))
    assert results.count(ErrorCode.CONFLICT) == 1 and len(s.rows) == 1


def test_transaction_rolls_back_row_and_ledger_on_event_failure(setup):
    s, service = setup
    s.fail_event = True
    with pytest.raises(RuntimeError):
        service.create(A, create_body(), KEY)
    assert s.rows == s.keys == {}


@pytest.mark.parametrize(
    "fields",
    [
        {"reason": "민감한 개인 사연"},
        {"phone": "010-0000-0000"},
        {"role": "admin"},
        {"owner_id": str(A.user_id)},
        {"choice": "고충 상담"},
        {"attachments": ["x.pdf"]},
    ],
)
def test_no_sensitive_body_or_client_owned_fields(fields):
    with pytest.raises(ValidationError):
        create_body(**fields)


def test_default_router_is_unmounted_and_unconfigured_is_503():
    app = create_app(Settings(environment="test"))
    assert not any("student-life" in p for p in app.openapi()["paths"])
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        for path in ("/guides", "/me"):
            r = client.get("/api/v1/student-life" + path)
            assert r.status_code == 503 and r.headers["Cache-Control"] == "private, no-store"


def test_http_privacy_no_sensitive_routes_and_validation(setup):
    s, service = setup
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_life_actor] = lambda: A
    app.dependency_overrides[get_life_service] = lambda: service
    assert "LifeRequestRecord" not in app.openapi()["components"]["schemas"]
    with TestClient(app) as client:
        path = "/api/v1/student-life/me/requests"
        r = client.post(
            path, json=create_body().model_dump(mode="json"), headers={"Idempotency-Key": KEY}
        )
        assert r.status_code == 201 and r.json()["resource_version"] == 1
        assert "owner_id" not in r.text and str(A.user_id) not in r.text
        assert r.headers["Cache-Control"] == "private, no-store"
        assert client.post(path, json=create_body().model_dump(mode="json")).status_code == 400
        for denied_path in ("/cases", "/me/badges", "/admin/issue", "/protected-counseling"):
            assert client.post("/api/v1/student-life" + denied_path, json={}).status_code == 404
        assert client.get("/api/v1/student-life/guides?limit=51").status_code == 400
        s.grants[A.user_id] = LifeGrant(active=False, program_ids=[])
        assert client.get("/api/v1/student-life/me").status_code == 403


def test_http_error_cannot_leak_driver_details(setup):
    s, service = setup
    s.fail_event = True
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_life_actor] = lambda: A
    app.dependency_overrides[get_life_service] = lambda: service
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/student-life/me/requests",
            json=create_body().model_dump(mode="json"),
            headers={"Idempotency-Key": KEY},
        )
    assert r.status_code == 500 and "fictional-private-db-detail" not in r.text
    assert r.headers["Cache-Control"] == "private, no-store"


def test_cancel_policy_boundary_and_current_kind_are_rechecked(setup):
    s, service = setup
    row = service.create(A, create_body(), KEY)
    cancel = CancelInput(expected_revision=1, expected_policy_revision=1)
    s.policies[DORM] = s.policies[DORM].model_copy(update={"cancel_until": NOW})
    denied(ErrorCode.CONFLICT, lambda: service.change(A, row.id, cancel, KEY, True))
    s.policies[DORM] = s.policies[DORM].model_copy(update={"cancel_until": None})
    denied(ErrorCode.CONFLICT, lambda: service.change(A, row.id, cancel, KEY, True))
    s.policies[DORM] = s.policies[DORM].model_copy(update={"kind": "inquiry"})
    denied(ErrorCode.CONFLICT, lambda: service.change(A, row.id, cancel, KEY, True))


def test_same_key_is_isolated_between_actors_and_cancelled_requests_do_not_reappear(setup):
    s, service = setup
    s.policies[DORM] = s.policies[DORM].model_copy(update={"capacity": 2})
    one = service.create(A, create_body(), KEY)
    two = service.create(B, create_body(), KEY)
    assert one.id != two.id and len(s.rows) == 2
    cancelled = service.change(
        A, one.id, CancelInput(expected_revision=1, expected_policy_revision=1), KEY, True
    )
    assert service.create(A, create_body(), KEY).state == "cancelled"
    fresh = service.create(A, create_body(), KEY + "new")
    assert fresh.id != cancelled.id and fresh.state == "requested"


def test_clock_and_policy_cannot_be_naive_or_cross_kind(setup):
    s, _ = setup
    naive = StudentLifeService(s, clock=lambda: NOW.replace(tzinfo=None))
    denied(ErrorCode.UNAVAILABLE, lambda: naive.create(A, create_body(), KEY))
    with pytest.raises(ValidationError):
        DemoLifePolicy(
            **(s.policies[DORM].model_dump() | {"allowed_choices": ["process_information"]})
        )
    with pytest.raises(ValidationError):
        LifeRequestRecord(
            id=uuid4(),
            owner_id=A.user_id,
            program_id=DORM,
            kind="dorm",
            choice="demo_dorm_a",
            state="answered",
            answer_code="demo_information_referred",
            revision=1,
            policy_revision=1,
            created_at=NOW,
            updated_at=NOW,
        )
