"""TC-V1-ADMIS-001~006 safe subset; no official decisions, money or live DB."""

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
from app.features.admissions.models import (
    AdmissionGuide,
    ApplicantActor,
    ApplicantGrant,
    DemoAdmissionPolicy,
    DemoTrack,
    DraftCreate,
    DraftUpdate,
    TransitionInput,
)
from app.features.admissions.router import get_admissions_service, get_applicant_actor, router
from app.features.admissions.service import AdmissionsService
from app.schemas.common import ErrorCode

NOW = datetime(2026, 10, 30, tzinfo=UTC)
A, B = ApplicantActor(user_id=uuid4()), ApplicantActor(user_id=uuid4())
CYCLE, TRACK = uuid4(), uuid4()
KEY = "demo-intent-key-12345"


class Store:
    """Test-only serial transaction fake; does not validate MariaDB locks or GRANTs."""

    def __init__(self):
        self.lock = RLock()
        self.rows, self.keys, self.guides_rows = {}, {}, []
        self.grants = {
            a.user_id: ApplicantGrant(active=True, applicant=True, cycle_ids={CYCLE})
            for a in (A, B)
        }
        self.policies = {
            CYCLE: DemoAdmissionPolicy(
                cycle_id=CYCLE,
                name="테스트 가상 모집",
                revision=1,
                tracks=[DemoTrack(id=TRACK, label="가상 프로젝트 전형")],
                opens_at=NOW - timedelta(days=1),
                closes_at=NOW + timedelta(days=1),
                withdrawal_closes_at=NOW + timedelta(days=2),
                max_applications=1,
            )
        }
        self.fail_event = False

    def guides(self, offset, limit):
        return self.guides_rows[offset : offset + limit]

    @contextmanager
    def transaction(self, user_id):
        with self.lock:
            rows, keys = dict(self.rows), dict(self.keys)
            try:
                yield Transaction(self, user_id)
            except BaseException:
                self.rows, self.keys = rows, keys
                raise


class Transaction:
    def __init__(self, store, user):
        self.store, self.user = store, user
        self.grant = store.grants.get(
            user, ApplicantGrant(active=False, applicant=False, cycle_ids=[])
        )

    def policies(self):
        return list(self.store.policies.values())

    def policy(self, cycle):
        return self.store.policies.get(cycle)

    def applications(self):
        return list(self.store.rows.values())

    def get(self, id):
        return self.store.rows.get(id)

    def replay(self, op, key, digest):
        old = self.store.keys.get((self.user, op, key))
        if old and old[0] != digest:
            raise ApiError(ErrorCode.CONFLICT)
        return old[1] if old else None

    def remember(self, row, op, key, digest):
        self.store.rows[row.id] = row
        if self.store.fail_event:
            raise RuntimeError("fictional-private-event-error")
        self.store.keys[self.user, op, key] = digest, row.id
        return row

    def create(self, row, op, key, digest):
        assert row.owner_id == self.user
        return self.remember(row, op, key, digest)

    def replace(self, row, expected, op, key, digest):
        current = self.store.rows.get(row.id)
        if (
            current is None
            or current.owner_id != self.user
            or current.revision != expected
            or current.cycle_id != row.cycle_id
        ):
            raise ApiError(ErrorCode.CONFLICT)
        return self.remember(row, op, key, digest)


@pytest.fixture
def setup():
    store = Store()
    return store, AdmissionsService(store, clock=lambda: NOW)


def body(**changes):
    return DraftCreate(
        **(
            {
                "cycle_id": CYCLE,
                "track_id": TRACK,
                "demo_alias": "가상 지원자 A",
                "motivation": "career_exploration",
                "expected_policy_revision": 1,
            }
            | changes
        )
    )


def transition(revision=1, policy_revision=1):
    return TransitionInput(expected_revision=revision, expected_policy_revision=policy_revision)


def denied(code, callback):
    with pytest.raises(ApiError) as error:
        callback()
    assert error.value.code == code


def test_unknown_guides_are_empty_not_invented(setup):
    store, service = setup
    assert service.guides(0, 20).items == []
    store.guides_rows = [AdmissionGuide(id=uuid4(), title="근거 미확인", summary="", revision=1)]
    result = service.guides(0, 20).items[0]
    assert result.source_kind == "UNKNOWN" and result.source_url is None


@pytest.mark.parametrize(
    "changes",
    [
        {"source_kind": "OFFICIAL_PUBLIC"},
        {"source_kind": "OFFICIAL_PUBLIC", "source_url": "javascript:alert(1)", "checked_at": NOW},
        {
            "source_kind": "OFFICIAL_PUBLIC",
            "source_url": "https://user:pass@example.test",
            "checked_at": NOW,
        },
        {
            "source_kind": "OFFICIAL_PUBLIC",
            "source_url": "https://example.test:bad",
            "checked_at": NOW,
        },
        {"source_kind": "DEMO", "source_url": "https://example.test", "checked_at": NOW},
        {
            "source_kind": "OFFICIAL_PUBLIC",
            "source_url": "https://example.test",
            "checked_at": NOW.replace(tzinfo=None),
        },
    ],
)
def test_false_official_citations_rejected(changes):
    with pytest.raises(ValidationError):
        AdmissionGuide(id=uuid4(), title="가상 안내", summary="", revision=1, **changes)


def test_cited_guide_preserves_revision_schedule_and_faq():
    guide = AdmissionGuide(
        id=uuid4(),
        title="테스트 공개자료 DTO",
        summary="실제 학교 자료 아님",
        revision=2,
        source_kind="OFFICIAL_PUBLIC",
        source_url="https://example.test/guide",
        checked_at=NOW,
        schedules=[{"label": "테스트 일정", "starts_at": NOW, "ends_at": NOW + timedelta(hours=1)}],
        faqs=[{"question": "테스트 질문", "answer": "테스트 답변"}],
    )
    assert guide.revision == 2 and len(guide.schedules) == len(guide.faqs) == 1


def test_create_update_submit_and_withdraw_are_demo_only(setup):
    store, service = setup
    row = service.create(A, body(), KEY)
    assert row.state == "draft" and "owner_id" not in row.model_dump()
    assert row.documents == row.admission_result == row.payment_refund == "BLOCKED"
    updated = service.change(
        A,
        row.id,
        DraftUpdate(**body().model_dump(exclude={"cycle_id"}), expected_revision=1),
        KEY,
        "update",
    )
    assert updated.revision == 2
    submitted = service.change(A, row.id, transition(2), KEY, "submit")
    assert (submitted.state, submitted.revision) == ("submitted", 3)
    withdrawn = service.change(A, row.id, transition(3), KEY, "withdraw")
    assert withdrawn.state == "withdrawal_requested" and withdrawn.revision == 4
    assert len(store.rows) == 1


def test_received_is_read_only_external_fixture_not_automatic_decision(setup):
    store, service = setup
    row = service.create(A, body(), KEY)
    store.rows[row.id] = store.rows[row.id].model_copy(update={"state": "received", "revision": 2})
    assert service.overview(A).applications[0].state == "received"
    withdrawn = service.change(A, row.id, transition(2), KEY, "withdraw")
    assert withdrawn.state == "withdrawal_requested"
    denied(ErrorCode.UNAVAILABLE, lambda: service.change(A, row.id, transition(3), KEY, "receive"))


def test_own_scope_parent_cycle_and_current_grant_are_rechecked(setup):
    store, service = setup
    row = service.create(A, body(), KEY)
    assert service.overview(B).applications == []
    denied(ErrorCode.NOT_FOUND, lambda: service.change(B, row.id, transition(), KEY, "submit"))
    denied(ErrorCode.NOT_FOUND, lambda: service.create(A, body(cycle_id=uuid4()), KEY + "x"))
    store.grants[A.user_id] = ApplicantGrant(active=True, applicant=True, cycle_ids=[])
    denied(ErrorCode.NOT_FOUND, lambda: service.create(A, body(), KEY))
    store.grants[A.user_id] = ApplicantGrant(active=False, applicant=True, cycle_ids={CYCLE})
    denied(ErrorCode.FORBIDDEN, lambda: service.overview(A))


def test_replay_and_changed_payload_and_revision_conflicts(setup):
    store, service = setup
    row = service.create(A, body(), KEY)
    assert service.create(A, body(), KEY).id == row.id
    denied(ErrorCode.CONFLICT, lambda: service.create(A, body(demo_alias="가상 지원자 B"), KEY))
    first = service.change(A, row.id, transition(), KEY, "submit")
    assert service.change(A, row.id, transition(), KEY, "submit") == first
    denied(
        ErrorCode.CONFLICT, lambda: service.change(A, row.id, transition(), KEY + "new", "withdraw")
    )
    assert len(store.rows) == 1


def test_replay_never_resurrects_removed_resource(setup):
    store, service = setup
    row = service.create(A, body(), KEY)
    del store.rows[row.id]
    denied(ErrorCode.NOT_FOUND, lambda: service.create(A, body(), KEY))
    assert store.rows == {}


def test_actor_namespace_and_transaction_rollback(setup):
    store, service = setup
    assert service.create(A, body(), KEY).id != service.create(B, body(), KEY).id
    store.rows, store.keys = {}, {}
    store.fail_event = True
    with pytest.raises(RuntimeError):
        service.create(A, body(), KEY)
    assert store.rows == store.keys == {}


def test_concurrent_create_limit_and_same_key(setup):
    store, service = setup

    def create(key):
        try:
            return service.create(A, body(), key).id
        except ApiError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        same = list(executor.map(create, [KEY, KEY]))
    assert same[0] == same[1] and len(store.rows) == 1
    denied(ErrorCode.CONFLICT, lambda: service.create(A, body(), KEY + "new"))


def test_window_track_and_policy_version_are_required(setup):
    store, service = setup
    denied(ErrorCode.CONFLICT, lambda: service.create(A, body(expected_policy_revision=2), KEY))
    denied(ErrorCode.VALIDATION, lambda: service.create(A, body(track_id=uuid4()), KEY))
    expired = AdmissionsService(store, clock=lambda: NOW + timedelta(days=1))
    denied(ErrorCode.CONFLICT, lambda: expired.create(A, body(), KEY))
    del store.policies[CYCLE]
    denied(ErrorCode.UNAVAILABLE, lambda: service.create(A, body(), KEY))


def test_changed_policy_requires_draft_review_before_submit(setup):
    store, service = setup
    row = service.create(A, body(), KEY)
    store.policies[CYCLE] = store.policies[CYCLE].model_copy(update={"revision": 2})
    denied(ErrorCode.CONFLICT, lambda: service.change(A, row.id, transition(1, 2), KEY, "submit"))
    edit = DraftUpdate(
        **body(expected_policy_revision=2).model_dump(exclude={"cycle_id"}), expected_revision=1
    )
    changed = service.change(A, row.id, edit, KEY, "update")
    assert (
        service.change(A, row.id, transition(changed.revision, 2), KEY, "submit").state
        == "submitted"
    )


def test_no_institutional_or_sensitive_fields_allowed():
    for values in (
        {"demo_alias": "실명 입력"},
        {"motivation": "010-1234-5678"},
        {"role": "admin"},
        {"owner_id": str(A.user_id)},
        {"documents": ["secret.pdf"]},
    ):
        with pytest.raises(ValidationError):
            body(**values)


def test_router_is_unmounted_and_default_dependencies_fail_closed():
    app = create_app(Settings(environment="test"))
    assert not any("admissions" in path for path in app.openapi()["paths"])
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        for path in ("/guides", "/me"):
            response = client.get("/api/v1/admissions" + path)
            assert response.status_code == 503
            assert response.headers["Cache-Control"] == "private, no-store"


def test_http_projection_validation_cache_and_no_hidden_officer_routes(setup):
    store, service = setup
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_applicant_actor] = lambda: A
    app.dependency_overrides[get_admissions_service] = lambda: service
    assert "ApplicationRecord" not in app.openapi()["components"]["schemas"]
    with TestClient(app) as client:
        payload = body().model_dump(mode="json")
        create = client.post(
            "/api/v1/admissions/me/applications", json=payload, headers={"Idempotency-Key": KEY}
        )
        assert create.status_code == 201 and create.headers["Cache-Control"] == "private, no-store"
        assert "owner_id" not in create.text and str(A.user_id) not in create.text
        bad = client.post("/api/v1/admissions/me/applications", json=payload)
        assert bad.status_code == 400 and bad.headers["Cache-Control"] == "private, no-store"
        assert client.get("/api/v1/admissions/guides?limit=51").status_code == 400
        id = create.json()["data"]["id"]
        assert (
            client.post(f"/api/v1/admissions/me/applications/{id}/receive", json={}).status_code
            == 404
        )
        assert (
            client.post(
                "/api/v1/admissions/me/applications/not-a-uuid/submit",
                json=transition().model_dump(),
                headers={"Idempotency-Key": KEY},
            ).status_code
            == 400
        )
        store.grants[A.user_id] = ApplicantGrant(active=False, applicant=False, cycle_ids=[])
        assert client.get("/api/v1/admissions/me").status_code == 403


def test_internal_failure_response_does_not_expose_payload(setup):
    store, service = setup
    store.fail_event = True
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_applicant_actor] = lambda: A
    app.dependency_overrides[get_admissions_service] = lambda: service
    with TestClient(app) as client:
        result = client.post(
            "/api/v1/admissions/me/applications",
            json=body().model_dump(mode="json"),
            headers={"Idempotency-Key": KEY},
        )
    assert result.status_code == 500 and "fictional-private-event-error" not in result.text
    assert result.headers["Cache-Control"] == "private, no-store"
