from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.admin_audit_queue.models import (
    AuditActor,
    AuditCategory,
    AuditPatchInput,
    AuditStatus,
    Classification,
    NoteCode,
    Resolution,
)
from app.features.admin_audit_queue.router import get_admin_audit_actor, router
from app.features.admin_audit_queue.service import AdminAuditQueueService
from app.schemas.common import ErrorCode

REVIEWER, OTHER, STRANGER = (AuditActor(user_id=uuid4()) for _ in range(3))
BASE = "/api/v1/admin-audit-queue"
KEY = "demo-key-1234567890"


class Grants:
    """Test-only grant port. Mutable to prove can_review is re-checked per operation."""

    def __init__(self):
        self.allowed = {REVIEWER.user_id, OTHER.user_id}
        self.calls = 0

    def __call__(self, user_id):
        self.calls += 1
        return user_id in self.allowed


def classify(revision=1, value="NO_ACTION", note="DEMO_CHECKED"):
    return {"revision": revision, "classification": value, "note_code": note}


def resolve(revision=2, value="KEEP_DEMO", note="DEMO_POLICY_REVIEW"):
    return {"revision": revision, "resolution": value, "note_code": note}


def make_app(service=None, actor=REVIEWER):
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    if service is not None:
        app.state.admin_audit_queue = service
    if actor is not None:
        app.dependency_overrides[get_admin_audit_actor] = lambda: actor
    return app


@pytest.fixture
def grants():
    return Grants()


@pytest.fixture
def service(grants):
    return AdminAuditQueueService(grants)


@pytest.fixture
def client(service):
    with TestClient(make_app(service)) as test_client:
        yield test_client


def first_id(client, **params):
    response = client.get(BASE, params=params)
    assert response.status_code == 200
    return response.json()["data"]["items"][0]["id"]


def assert_error(response, status, code):
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.headers["Cache-Control"] == "private, no-store"


def test_not_mounted_and_default_dependencies_return_503_no_store(service):
    plain = create_app(Settings(environment="test"))
    assert all("/admin-audit-queue" not in getattr(route, "path", "") for route in plain.routes)
    item = str(uuid4())
    # Default actor dependency is dormant even if a service exists.
    with TestClient(make_app(service, actor=None)) as test_client:
        for method, path in [("get", BASE), ("get", f"{BASE}/{item}")]:
            assert_error(getattr(test_client, method)(path), 503, "UNAVAILABLE")
        assert_error(test_client.patch(f"{BASE}/{item}", json=classify()), 503, "UNAVAILABLE")
    # Actor present but no app.state service, or a wrong type, is also 503.
    with TestClient(make_app(None)) as test_client:
        assert_error(test_client.get(BASE), 503, "UNAVAILABLE")
    wrong = make_app(None)
    wrong.state.admin_audit_queue = object()
    with TestClient(wrong) as test_client:
        assert_error(test_client.get(BASE), 503, "UNAVAILABLE")


def test_list_returns_fixed_demo_metadata_only(client):
    response = client.get(BASE)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    page = response.json()["data"]
    meta = {
        "source_kind": "DEMO",
        "storage": "PROCESS_MEMORY",
        "official_effect": False,
        "restart_reset": True,
    }
    assert page["meta"] == meta
    assert len(page["items"]) == 6
    for item in page["items"]:
        assert set(item) == {
            "id",
            "category",
            "demo_label",
            "status",
            "classification",
            "resolution",
            "note_code",
            "revision",
            "meta",
        }
        assert item["status"] == "PENDING" and item["revision"] == 1 and item["meta"] == meta
    body = response.text
    for forbidden in ("author", "owner", "user_id", "content", "name", str(REVIEWER.user_id)):
        assert forbidden not in body


def test_fixture_is_deterministic_per_actor_and_restart_resets(grants):
    first = AdminAuditQueueService(grants).list_items(REVIEWER)
    again = AdminAuditQueueService(grants).list_items(REVIEWER)
    other = AdminAuditQueueService(grants).list_items(OTHER)
    assert [i.id for i in first.items] == [i.id for i in again.items]
    assert {i.id for i in first.items}.isdisjoint({i.id for i in other.items})
    service = AdminAuditQueueService(grants)
    item = service.list_items(REVIEWER).items[0]
    service.patch(REVIEWER, item.id, AuditPatchInput(**classify()))
    fresh = AdminAuditQueueService(grants).get(REVIEWER, item.id)
    assert fresh.status is AuditStatus.PENDING and fresh.revision == 1


def test_enum_filters_and_invalid_filters(client):
    reports = client.get(BASE, params={"category": "REPORT"}).json()["data"]["items"]
    assert reports and all(i["category"] == "REPORT" for i in reports)
    item = reports[0]["id"]
    client.patch(f"{BASE}/{item}", json=classify())
    classified = client.get(BASE, params={"status": "CLASSIFIED"}).json()["data"]["items"]
    assert [i["id"] for i in classified] == [item]
    both = client.get(BASE, params={"status": "PENDING", "category": "REPORT"}).json()["data"]
    assert item not in [i["id"] for i in both["items"]]
    for params in ({"status": "pending"}, {"category": "USER"}, {"status": "DELETED"}):
        assert_error(client.get(BASE, params=params), 400, "VALIDATION")


def test_full_lifecycle_cas_and_resolved_immutable(client):
    item = first_id(client)
    path = f"{BASE}/{item}"
    classified = client.patch(path, json=classify(value="REVIEW_NEEDED"))
    assert classified.status_code == 200
    assert classified.headers["Cache-Control"] == "private, no-store"
    data = classified.json()["data"]
    assert data["status"] == "CLASSIFIED" and data["revision"] == 2
    assert data["classification"] == "REVIEW_NEEDED" and data["resolution"] is None
    assert_error(client.patch(path, json=resolve(revision=1)), 409, "CONFLICT")
    assert_error(client.patch(path, json=resolve(revision=3)), 409, "CONFLICT")
    resolved = client.patch(path, json=resolve(value="RESOLVE_DEMO")).json()["data"]
    assert resolved["status"] == "RESOLVED" and resolved["revision"] == 3
    assert (
        resolved["classification"] == "REVIEW_NEEDED" and resolved["resolution"] == "RESOLVE_DEMO"
    )
    assert resolved["meta"]["official_effect"] is False
    # Fresh GET matches receipt.
    assert client.get(path).json()["data"] == resolved
    for body in (resolve(revision=3), classify(revision=3)):
        assert_error(client.patch(path, json=body), 409, "CONFLICT")
    assert client.get(path).json()["data"]["revision"] == 3


def test_out_of_order_step_conflicts(client):
    item = first_id(client)
    assert_error(client.patch(f"{BASE}/{item}", json=resolve(revision=1)), 409, "CONFLICT")
    client.patch(f"{BASE}/{item}", json=classify())
    assert_error(client.patch(f"{BASE}/{item}", json=classify(revision=2)), 409, "CONFLICT")


@pytest.mark.parametrize(
    "body",
    [
        {"revision": 1, "note_code": "DEMO_CHECKED"},
        {**classify(), "resolution": "KEEP_DEMO"},
        {**classify(), "owner_id": str(uuid4())},
        {**classify(), "role": "ADMIN"},
        {**classify(), "body": "free text"},
        classify(revision="1"),
        classify(revision=True),
        classify(revision=1.0),
        classify(revision=0),
        classify(revision=1_000_001),
        classify(value="no_action"),
        classify(value="BAN_USER"),
        classify(note="FREEFORM"),
        {"revision": 1, "classification": "NO_ACTION"},
    ],
)
def test_strict_body_rejected_without_mutation(client, body):
    item = first_id(client)
    assert_error(client.patch(f"{BASE}/{item}", json=body), 400, "VALIDATION")
    assert client.get(f"{BASE}/{item}").json()["data"]["revision"] == 1


def test_invalid_path_and_unknown_id(client):
    assert_error(client.get(f"{BASE}/not-a-uuid"), 400, "VALIDATION")
    assert_error(client.get(f"{BASE}/{uuid4()}"), 404, "NOT_FOUND")
    assert_error(client.patch(f"{BASE}/{uuid4()}", json=classify()), 404, "NOT_FOUND")


def test_cross_owner_is_404_and_untouched(service):
    with TestClient(make_app(service, actor=OTHER)) as other_client:
        other_item = first_id(other_client)
    with TestClient(make_app(service, actor=REVIEWER)) as reviewer:
        assert_error(reviewer.get(f"{BASE}/{other_item}"), 404, "NOT_FOUND")
        assert_error(reviewer.patch(f"{BASE}/{other_item}", json=classify()), 404, "NOT_FOUND")
        assert other_item not in [i["id"] for i in reviewer.get(BASE).json()["data"]["items"]]
    # The service takes a UUID; the owner's own item is still revision 1 (untouched).
    assert service.get(OTHER, UUID(other_item)).revision == 1


def test_denied_or_failing_grant_never_allocates_owner_queue():
    for port in (lambda _user: False, lambda _user: 1, lambda _user: None):
        service = AdminAuditQueueService(port)
        for call in (
            lambda service=service: service.list_items(REVIEWER),
            lambda service=service: service.get(REVIEWER, uuid4()),
            lambda service=service: service.patch(
                REVIEWER, uuid4(), AuditPatchInput(**classify()), "intent-key-0001"
            ),
        ):
            with pytest.raises(ApiError) as denied:
                call()
            assert denied.value.code is ErrorCode.FORBIDDEN
        assert service._owners == {} and service._keys == {}

    def broken(_user):
        raise RuntimeError("backend down")

    service = AdminAuditQueueService(broken)
    with pytest.raises(ApiError) as failed:
        service.list_items(REVIEWER)
    assert failed.value.code is ErrorCode.UNAVAILABLE
    assert service._owners == {} and service._keys == {}


def test_can_review_is_evaluated_while_holding_store_lock():
    holder: list = []

    def port(_user):
        # RLock._is_owned is private but the stable way to observe ownership in CPython.
        holder.append(service._lock._is_owned())
        return True

    service = AdminAuditQueueService(port)
    item = service.list_items(REVIEWER).items[0].id
    service.get(REVIEWER, item)
    service.patch(REVIEWER, item, AuditPatchInput(**classify()), "intent-key-0002")
    service.patch(REVIEWER, item, AuditPatchInput(**classify()), "intent-key-0002")  # replay
    assert holder == [True, True, True, True]


def test_can_review_is_checked_on_every_operation(service, grants):
    with TestClient(make_app(service)) as test_client:
        item = first_id(test_client)
        before = grants.calls
        test_client.get(f"{BASE}/{item}")
        test_client.patch(f"{BASE}/{item}", json=classify())
        assert grants.calls == before + 2
        # Grant revoked between requests: current role/scope wins immediately, including PATCH.
        grants.allowed.discard(REVIEWER.user_id)
        assert_error(test_client.get(BASE), 403, "FORBIDDEN")
        assert_error(test_client.get(f"{BASE}/{item}"), 403, "FORBIDDEN")
        assert_error(test_client.patch(f"{BASE}/{item}", json=resolve()), 403, "FORBIDDEN")
    assert service.get(OTHER, service.list_items(OTHER).items[0].id).revision == 1
    with pytest.raises(ApiError) as denied:
        service.get(STRANGER, item)
    assert denied.value.code is ErrorCode.FORBIDDEN


def test_grant_port_must_return_true_and_failure_is_safe_503():
    truthy = AdminAuditQueueService(lambda _user: 1)
    with pytest.raises(ApiError) as error:
        truthy.list_items(REVIEWER)
    assert error.value.code is ErrorCode.FORBIDDEN

    def broken(_user):
        raise RuntimeError("secret backend detail")

    with TestClient(make_app(AdminAuditQueueService(broken))) as test_client:
        response = test_client.get(BASE)
        assert_error(response, 503, "UNAVAILABLE")
        assert "secret" not in response.text
    with pytest.raises(ApiError) as missing:
        AdminAuditQueueService(lambda _user: True).list_items(None)
    assert missing.value.code is ErrorCode.UNAUTHORIZED


def test_owner_cap_is_bounded(grants):
    service = AdminAuditQueueService(lambda _user: True, max_owners=2)
    service.list_items(REVIEWER)
    service.list_items(OTHER)
    with pytest.raises(ApiError) as full:
        service.list_items(STRANGER)
    assert full.value.code is ErrorCode.UNAVAILABLE
    assert len(service.list_items(REVIEWER).items) == 6


def test_idempotent_patch_replays_same_intent_and_rejects_reuse(client):
    item = first_id(client)
    headers = {"Idempotency-Key": KEY}
    first = client.patch(f"{BASE}/{item}", json=classify(), headers=headers)
    replay = client.patch(f"{BASE}/{item}", json=classify(), headers=headers)
    assert first.status_code == replay.status_code == 200
    assert first.json()["data"] == replay.json()["data"]
    assert client.get(f"{BASE}/{item}").json()["data"]["revision"] == 2
    assert_error(
        client.patch(f"{BASE}/{item}", json=classify(note="DEMO_POLICY_REVIEW"), headers=headers),
        409,
        "CONFLICT",
    )
    other = client.get(BASE).json()["data"]["items"][1]["id"]
    assert_error(client.patch(f"{BASE}/{other}", json=classify(), headers=headers), 409, "CONFLICT")
    for bad in ("short", "x" * 101, "has space in key!!"):
        assert_error(
            client.patch(f"{BASE}/{item}", json=resolve(), headers={"Idempotency-Key": bad}),
            400,
            "VALIDATION",
        )


def test_idempotency_keys_are_owner_scoped_and_bounded():
    service = AdminAuditQueueService(lambda _user: True, max_keys_per_owner=2)
    mine = service.list_items(REVIEWER).items
    theirs = service.list_items(OTHER).items
    service.patch(REVIEWER, mine[0].id, AuditPatchInput(**classify()), KEY)
    # Same key from another owner is independent and cannot replay the first owner's receipt.
    receipt = service.patch(OTHER, theirs[0].id, AuditPatchInput(**classify()), KEY)
    assert receipt.id == theirs[0].id
    service.patch(REVIEWER, mine[1].id, AuditPatchInput(**classify()), KEY + "-b")
    service.patch(REVIEWER, mine[2].id, AuditPatchInput(**classify()), KEY + "-c")
    assert len(service._keys[REVIEWER.user_id]) == 2
    # Evicted key is no longer a replay: stale revision now conflicts instead.
    with pytest.raises(ApiError) as evicted:
        service.patch(REVIEWER, mine[0].id, AuditPatchInput(**classify()), KEY)
    assert evicted.value.code is ErrorCode.CONFLICT


def test_concurrent_same_revision_patch_has_single_winner(service):
    item = service.list_items(REVIEWER).items[0].id
    body = AuditPatchInput(**classify())

    def attempt(_):
        try:
            return service.patch(REVIEWER, item, body).revision
        except ApiError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(16)))
    assert results.count(2) == 1
    assert results.count(ErrorCode.CONFLICT) == 15
    assert service.get(REVIEWER, item).revision == 2


def test_concurrent_new_owners_respect_cap():
    service = AdminAuditQueueService(lambda _user: True, max_owners=3)
    actors = [AuditActor(user_id=uuid4()) for _ in range(10)]

    def attempt(actor):
        try:
            service.list_items(actor)
            return True
        except ApiError:
            return False

    with ThreadPoolExecutor(max_workers=10) as pool:
        assert sum(pool.map(attempt, actors)) == 3
    assert len(service._owners) == 3


def test_model_rejects_exactly_one_step_violations():
    with pytest.raises(ValidationError):
        AuditPatchInput(revision=1, note_code=NoteCode.DEMO_CHECKED)
    with pytest.raises(ValidationError):
        AuditPatchInput(
            revision=1,
            classification=Classification.NO_ACTION,
            resolution=Resolution.KEEP_DEMO,
            note_code=NoteCode.DEMO_CHECKED,
        )
    assert {c.value for c in AuditCategory} == {"NOTICE", "POST", "REPORT"}
