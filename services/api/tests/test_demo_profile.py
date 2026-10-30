"""DEMO/PROCESS_MEMORY activity preferences (FR-AUTH-003 sandbox, TC-V1-AUTH-003 partial).

In-process store only; no DB, auth provider or network is involved. The actor override below is
a test-only stand-in for the shared common actor that the root owner injects.
"""

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from fastapi import Header
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.demo_profile import (
    PATH,
    DemoProfileStore,
    DemoProfileUpdate,
    get_actor,
    router,
)
from app.schemas.common import ErrorCode

API = f"/api/v1{PATH}"
USER_A = "00000000-0000-4000-8000-00000000000a"
USER_B = "00000000-0000-4000-8000-00000000000b"
USER_C = "00000000-0000-4000-8000-00000000000c"
DATA_KEYS = {"interests", "skill_level", "revision", "record_source", "storage"}
ERROR_KEYS = {"code", "message", "field_errors", "retryable", "request_id"}


def header_actor(x_test_user: str | None = Header(default=None)) -> UUID | None:
    return UUID(x_test_user) if x_test_user else None


def build(store: DemoProfileStore | None = None, *, actor=header_actor) -> TestClient:
    application = create_app(Settings(environment="test"))
    application.include_router(router, prefix="/api/v1")
    if actor is not None:
        application.dependency_overrides[get_actor] = actor
    if store is not None:
        application.state.demo_profile = store
    return TestClient(application, raise_server_exceptions=False)


@pytest.fixture
def store():
    return DemoProfileStore()


@pytest.fixture
def client(store):
    return build(store)


def as_user(user: str) -> dict[str, str]:
    return {"X-Test-User": user}


def patch(client, user=USER_A, **overrides):
    body = {"interests": ["coding"], "skill_level": "intermediate", "revision": 1, **overrides}
    return client.patch(API, json=body, headers=as_user(user))


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    assert response.headers["Cache-Control"] == "private, no-store"
    body = response.json()
    assert set(body) == ERROR_KEYS
    assert body["code"] == code


# ---------------------------------------------------------------- fail closed / ordering


@pytest.mark.parametrize("method", ["get", "patch"])
def test_default_dependencies_fail_closed(method):
    response = getattr(build(actor=None), method)(API, headers=as_user(USER_A))
    assert_error(response, 503, "UNAVAILABLE")


def test_missing_store_state_fails_closed():
    assert_error(build().get(API, headers=as_user(USER_A)), 503, "UNAVAILABLE")


def test_wrong_store_type_fails_closed():
    client = build()
    client.app.state.demo_profile = {"not": "a store"}
    assert_error(client.get(API, headers=as_user(USER_A)), 503, "UNAVAILABLE")


@pytest.mark.parametrize("method", ["get", "patch"])
def test_unauthenticated_is_401_before_store_is_resolved(method):
    # No store configured: authentication must still be decided first.
    response = getattr(build(), method)(API)
    assert_error(response, 401, "UNAUTHORIZED")


def test_non_uuid_actor_is_rejected(store):
    client = build(store, actor=lambda: USER_A)  # plain string, not a UUID
    assert_error(client.get(API), 401, "UNAUTHORIZED")


# ---------------------------------------------------------------- read / write / readback


def test_unwritten_owner_reads_fixed_synthetic_default_without_allocation(client, store):
    response = client.get(API, headers=as_user(USER_A))
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    body = response.json()
    assert set(body["data"]) == DATA_KEYS
    assert body["data"] == {
        "interests": [],
        "skill_level": "beginner",
        "revision": 1,
        "record_source": "DEMO",
        "storage": "PROCESS_MEMORY",
    }
    assert body["resource_version"] == 1
    assert store.owner_count() == 0


def test_patch_then_readback_with_canonical_interest_order(client):
    response = patch(client, interests=["career", "coding"])
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    saved = response.json()["data"]
    assert saved["interests"] == ["coding", "career"]
    assert saved["skill_level"] == "intermediate"
    assert saved["revision"] == 2
    assert client.get(API, headers=as_user(USER_A)).json()["data"] == saved


def test_empty_interest_list_is_allowed(client):
    response = patch(client, interests=[])
    assert response.status_code == 200
    assert response.json()["data"]["interests"] == []


def test_response_never_contains_owner_identity(client):
    text = patch(client).text + client.get(API, headers=as_user(USER_A)).text
    assert USER_A not in text


# ---------------------------------------------------------------- A/B isolation


def test_owners_are_isolated(client):
    assert patch(client, USER_A, interests=["design"]).status_code == 200
    b_view = client.get(API, headers=as_user(USER_B)).json()["data"]
    assert b_view["interests"] == [] and b_view["revision"] == 1

    response = patch(client, USER_B, interests=["volunteering"], skill_level="beginner")
    assert response.status_code == 200
    a_view = client.get(API, headers=as_user(USER_A)).json()["data"]
    assert a_view["interests"] == ["design"] and a_view["revision"] == 2
    b_view = client.get(API, headers=as_user(USER_B)).json()["data"]
    assert b_view["interests"] == ["volunteering"] and b_view["revision"] == 2


def test_client_supplied_owner_in_query_or_header_is_ignored(client):
    patch(client, USER_B, interests=["career"])
    response = client.get(
        f"{API}?user_id={USER_B}&owner={USER_B}",
        headers={**as_user(USER_A), "X-User-Id": USER_B, "X-Role": "admin"},
    )
    assert response.json()["data"]["interests"] == []


# ---------------------------------------------------------------- immutable fields / inputs


@pytest.mark.parametrize(
    "extra",
    [
        {"user_id": USER_B},
        {"owner": USER_B},
        {"display_name": "가상 이름"},
        {"name": "가상 이름"},
        {"bio": "자유 입력"},
        {"department": "가상 학과"},
        {"department_id": "dept-1"},
        {"academic_year": 2},
        {"student_id": "20260001"},
        {"role": "admin"},
        {"roles": ["operator"]},
        {"record_source": "OFFICIAL"},
        {"storage": "MARIADB"},
    ],
)
def test_identity_academic_and_role_inputs_are_rejected(client, store, extra):
    response = patch(client, **extra)
    assert_error(response, 400, "VALIDATION")
    assert store.owner_count() == 0
    assert client.get(API, headers=as_user(USER_A)).json()["data"]["revision"] == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"interests": ["gaming"]},
        {"interests": ["coding", "coding"]},
        {"interests": "coding"},
        {"interests": ["Coding"]},
        {"interests": ["coding", "design", "volunteering", "career", "coding"]},
        {"skill_level": "expert"},
        {"skill_level": None},
        {"revision": "1"},
        {"revision": True},
        {"revision": 0},
        {"revision": -1},
        {"revision": 1.0},
    ],
)
def test_invalid_inputs_are_rejected(client, store, overrides):
    assert_error(patch(client, **overrides), 400, "VALIDATION")
    assert store.owner_count() == 0


@pytest.mark.parametrize("missing", ["interests", "skill_level", "revision"])
def test_missing_fields_are_rejected(client, missing):
    body = {"interests": [], "skill_level": "beginner", "revision": 1}
    body.pop(missing)
    assert_error(client.patch(API, json=body, headers=as_user(USER_A)), 400, "VALIDATION")


def test_non_json_body_is_rejected(client):
    response = client.patch(
        API,
        content=b"interests=coding",
        headers={**as_user(USER_A), "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert_error(response, 400, "VALIDATION")


# ---------------------------------------------------------------- CAS / capacity


def test_stale_revision_is_409_and_keeps_current_state(client):
    assert patch(client, interests=["design"]).status_code == 200
    assert_error(patch(client, interests=["career"], revision=1), 409, "CONFLICT")
    assert_error(patch(client, interests=["career"], revision=3), 409, "CONFLICT")
    current = client.get(API, headers=as_user(USER_A)).json()["data"]
    assert current["interests"] == ["design"] and current["revision"] == 2
    assert patch(client, interests=["career"], revision=2).json()["data"]["revision"] == 3


def test_owner_capacity_is_bounded():
    store = DemoProfileStore(max_owners=2)
    client = build(store)
    assert patch(client, USER_A).status_code == 200
    assert patch(client, USER_B).status_code == 200
    assert_error(patch(client, USER_C), 503, "UNAVAILABLE")
    # Existing owners keep writing and new owners can still read the default.
    assert patch(client, USER_A, revision=2).status_code == 200
    assert client.get(API, headers=as_user(USER_C)).json()["data"]["revision"] == 1
    assert store.owner_count() == 2


@pytest.mark.parametrize("max_owners", [0, 201])
def test_store_constructor_rejects_unbounded_capacity(max_owners):
    with pytest.raises(ValueError):
        DemoProfileStore(max_owners=max_owners)


def test_concurrent_same_revision_writes_have_one_winner():
    store = DemoProfileStore()
    owner = UUID(USER_A)
    payload = DemoProfileUpdate(interests=["coding"], skill_level="beginner", revision=1)

    def attempt(_: int) -> bool:
        try:
            store.update(owner, payload)
            return True
        except ApiError as exc:
            assert exc.code is ErrorCode.CONFLICT
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(32)))
    assert results.count(True) == 1
    assert store.get(owner).revision == 2


def test_fresh_store_resets_like_a_process_restart():
    first = DemoProfileStore()
    first.update(
        UUID(USER_A), DemoProfileUpdate(interests=["career"], skill_level="beginner", revision=1)
    )
    assert DemoProfileStore().get(UUID(USER_A)).revision == 1
