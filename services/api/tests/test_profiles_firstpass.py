from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.profiles.models import (
    ActivityProfileRecord,
    CurrentProfileAccess,
    ProfileActor,
    ProfileEditPolicy,
    ProfileUpdate,
)
from app.features.profiles.ports import ProfileConflict
from app.features.profiles.router import get_profile_actor, get_profile_service, router
from app.features.profiles.service import ProfileService
from app.schemas.common import ErrorCode

NOW = datetime(2026, 10, 30, tzinfo=UTC)
ACTOR, OTHER = ProfileActor(user_id=uuid4()), ProfileActor(user_id=uuid4())
KEY = "profile-intent-key-0001"


class FakeStore:
    def __init__(self):
        self.lock = RLock()
        self.rows = {
            actor.user_id: ActivityProfileRecord(
                user_id=actor.user_id,
                display_name="가상 읽기전용 실명",
                department_name="가상 학과",
                academic_year=1,
                skills=[],
                interests=[],
                bio="",
                revision=1,
                updated_at=NOW,
            )
            for actor in (ACTOR, OTHER)
        }
        self.access = {
            actor.user_id: CurrentProfileAccess(
                user_id=actor.user_id, active=True, current_student=True
            )
            for actor in (ACTOR, OTHER)
        }
        self.policy = ProfileEditPolicy(revision=1, editable_fields={"skills", "interests", "bio"})
        self.receipts, self.events = {}, []
        self.fail_after_write = False

    @contextmanager
    def transaction(self, actor_id):
        with self.lock:
            snapshot = deepcopy((self.rows, self.receipts, self.events))
            try:
                yield FakeTransaction(self, actor_id)
            except BaseException:
                self.rows, self.receipts, self.events = snapshot
                raise


class FakeTransaction:
    def __init__(self, store, actor_id):
        self.store, self.actor_id = store, actor_id

    @property
    def access(self):
        return self.store.access[self.actor_id]

    @property
    def policy(self):
        return self.store.policy

    def self_profile(self):
        return self.store.rows.get(self.actor_id)

    def replay(self, key, body_hash):
        prior = self.store.receipts.get((self.actor_id, key))
        if prior and prior != body_hash:
            raise ProfileConflict()
        return prior is not None

    def save(self, row, expected_revision, key, body_hash):
        current = self.self_profile()
        if current is None or current.revision != expected_revision or row.user_id != self.actor_id:
            raise ProfileConflict()
        self.store.rows[self.actor_id] = row
        self.store.receipts[self.actor_id, key] = body_hash
        self.store.events.append((self.actor_id, row.revision))
        if self.store.fail_after_write:
            raise RuntimeError("PRIVATE-BIO-DO-NOT-LOG")
        return row


@pytest.fixture
def setup():
    store = FakeStore()
    return store, ProfileService(store, clock=lambda: NOW)


def change(**updates):
    return ProfileUpdate(
        **(
            {
                "skills": ["Python"],
                "interests": ["가상 협업"],
                "bio": "가상 소개",
                "expected_revision": 1,
                "expected_policy_revision": 1,
            }
            | updates
        )
    )


def denied(code, callback):
    with pytest.raises(ApiError) as error:
        callback()
    assert error.value.code == code


def test_reads_only_self_and_writes_only_activity_fields(setup):
    store, service = setup
    before = service.get(ACTOR)
    updated = service.update(ACTOR, change(), KEY)
    assert updated.skills == ["Python"] and updated.revision == 2
    assert (updated.display_name, updated.department_name, updated.academic_year) == (
        before.display_name,
        before.department_name,
        before.academic_year,
    )
    assert service.get(OTHER).bio == ""
    assert updated.visibility == "SELF_ONLY" and updated.identity_editable is False
    assert "user_id" not in updated.model_dump() and "role" not in updated.model_dump()
    assert len(store.events) == 1


def test_exact_replay_and_changed_body_and_actor_key_scope(setup):
    store, service = setup
    service.update(ACTOR, change(), KEY)
    assert service.update(ACTOR, change(), KEY).replayed
    denied(ErrorCode.CONFLICT, lambda: service.update(ACTOR, change(bio="different"), KEY))
    assert service.update(OTHER, change(), KEY).revision == 2
    assert len(store.events) == 2


@pytest.mark.parametrize(
    "field",
    [
        "user_id",
        "display_name",
        "academic_year",
        "department_id",
        "role",
        "status",
        "nickname",
        "record_source",
    ],
)
def test_identity_privilege_and_new_product_fields_are_rejected(field):
    with pytest.raises(ValidationError):
        ProfileUpdate(**change().model_dump(), **{field: "untrusted"})


@pytest.mark.parametrize(
    "case,code",
    [
        ("inactive", ErrorCode.UNAUTHORIZED),
        ("foreign", ErrorCode.UNAUTHORIZED),
        ("not_student", ErrorCode.FORBIDDEN),
        ("missing_policy", ErrorCode.UNAVAILABLE),
        ("missing_profile", ErrorCode.NOT_FOUND),
        ("foreign_row", ErrorCode.NOT_FOUND),
    ],
)
def test_current_access_is_checked_before_read_or_replay(setup, case, code):
    store, service = setup
    service.update(ACTOR, change(), KEY)
    if case == "inactive":
        store.access[ACTOR.user_id].active = False
    elif case == "foreign":
        store.access[ACTOR.user_id].user_id = OTHER.user_id
    elif case == "not_student":
        store.access[ACTOR.user_id].current_student = False
    elif case == "missing_policy":
        store.policy = None
    elif case == "missing_profile":
        del store.rows[ACTOR.user_id]
    else:
        store.rows[ACTOR.user_id] = store.rows[OTHER.user_id]
    denied(code, lambda: service.get(ACTOR))
    denied(code, lambda: service.update(ACTOR, change(), KEY))


def test_current_policy_restriction_and_revision_apply_before_replay(setup):
    store, service = setup
    service.update(ACTOR, change(), KEY)
    store.policy.editable_fields = frozenset()
    assert service.update(ACTOR, change(), KEY).replayed  # no forbidden field changes
    denied(
        ErrorCode.FORBIDDEN,
        lambda: service.update(ACTOR, change(bio="new", expected_revision=2), KEY + "2"),
    )
    store.policy.revision = 2
    denied(ErrorCode.CONFLICT, lambda: service.update(ACTOR, change(), KEY))


def test_cas_and_missing_row_replay_never_provision(setup):
    store, service = setup
    service.update(ACTOR, change(), KEY)
    denied(ErrorCode.CONFLICT, lambda: service.update(ACTOR, change(), KEY + "2"))
    del store.rows[ACTOR.user_id]
    denied(ErrorCode.NOT_FOUND, lambda: service.update(ACTOR, change(), KEY))
    assert ACTOR.user_id not in store.rows


def test_row_receipt_event_rollback_together(setup):
    store, service = setup
    store.fail_after_write = True
    with pytest.raises(RuntimeError):
        service.update(ACTOR, change(), KEY)
    assert store.rows[ACTOR.user_id].revision == 1 and not store.receipts and not store.events


@pytest.mark.parametrize(
    "body",
    [{"skills": ["same", "SAME"]}, {"interests": [""]}, {"skills": ["x" * 31]}, {"bio": "x" * 501}],
)
def test_tag_and_bio_limits_and_duplicates(body):
    with pytest.raises(ValidationError):
        change(**body)
    assert change(bio="🙂" * 500).bio == "🙂" * 500


def test_invalid_key_and_naive_clock_fail_closed(setup):
    store, service = setup
    denied(ErrorCode.VALIDATION, lambda: service.update(ACTOR, change(), "bad"))
    denied(
        ErrorCode.UNAVAILABLE,
        lambda: ProfileService(store, clock=lambda: NOW.replace(tzinfo=None)).update(
            ACTOR, change(), KEY
        ),
    )
    assert not store.receipts


def test_concurrent_fake_uow_retries_one_update_not_mariadb_proof(setup):
    store, service = setup
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda _: service.update(ACTOR, change(), KEY), range(4)))
    assert {row.revision for row in rows} == {2}
    assert len(store.events) == len(store.receipts) == 1


def client(service=None):
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    if service:
        app.dependency_overrides[get_profile_actor] = lambda: ACTOR
        app.dependency_overrides[get_profile_service] = lambda: service
    return TestClient(app)


def test_default_unmounted_and_dependency_503():
    with TestClient(create_app(Settings(environment="test"))) as app:
        assert app.get("/api/v1/profiles/me").status_code == 404
    with client() as app:
        response = app.get("/api/v1/profiles/me")
        assert (
            response.status_code == 503 and response.headers["cache-control"] == "private, no-store"
        )


def test_http_private_projection_input_and_error_cache(setup, caplog):
    store, service = setup
    with client(service) as app:
        assert app.get("/api/v1/profiles/me").headers["cache-control"] == "private, no-store"
        body = change().model_dump(mode="json")
        result = app.put("/api/v1/profiles/me", json=body, headers={"Idempotency-Key": KEY})
        assert result.status_code == 200 and "user_id" not in result.json()["data"]
        for bad in [{**body, "display_name": "fake realname"}, {**body, "role": "admin"}]:
            result = app.put("/api/v1/profiles/me", json=bad, headers={"Idempotency-Key": KEY})
            assert (
                result.status_code == 400 and result.headers["cache-control"] == "private, no-store"
            )
        store.access[ACTOR.user_id].active = False
        assert app.get("/api/v1/profiles/me").status_code == 401
        store.access[ACTOR.user_id].active = True
        store.fail_after_write = True
        result = app.put(
            "/api/v1/profiles/me",
            json=change(expected_revision=2).model_dump(mode="json"),
            headers={"Idempotency-Key": KEY + "2"},
        )
        assert result.status_code == 500 and result.headers["cache-control"] == "private, no-store"
        assert "PRIVATE-BIO" not in result.text + caplog.text
