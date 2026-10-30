from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.demo_channels.models import (
    DemoChannelRequestCreate,
    RequestedKind,
    RequestStatus,
)
from app.features.demo_channels.router import get_actor, router
from app.features.demo_channels.store import DemoChannelsStore
from app.schemas.common import ErrorCode

NOW = datetime(2026, 10, 30, tzinfo=UTC)
ACTOR, OTHER = uuid4(), uuid4()
PATH = "/api/v1/me/demo-channels"


def body(**updates):
    return {"purpose": "study", "requested_kind": "FREE", "consent": True} | updates


def make(**updates):
    return DemoChannelRequestCreate(**body(**updates))


def denied(code, callback):
    with pytest.raises(ApiError) as error:
        callback()
    assert error.value.code == code


@pytest.fixture
def store():
    return DemoChannelsStore(clock=lambda: NOW)


def test_free_is_created_and_official_stays_pending_without_badge(store):
    free = store.create(ACTOR, make())
    official = store.create(ACTOR, make(requested_kind="OFFICIAL", purpose="project"))
    assert free.status is RequestStatus.CREATED
    assert official.status is RequestStatus.PENDING_REVIEW
    for view in (free, official):
        dumped = view.model_dump()
        assert dumped["official_badge"] is False and dumped["real_review"] == "NOT_OPERATED"
        assert dumped["record_source"] == "DEMO" and dumped["persistence"] == "PROCESS_MEMORY"
        assert "owner_id" not in dumped and "role" not in dumped
        assert view.title.startswith("[DEMO] ")
    # No transition API exists: the store exposes only list/create/cancel.
    public = {name for name in dir(store) if not name.startswith("_")}
    assert public == {"list_own", "create", "cancel"}
    assert [row.status for row in store.list_own(ACTOR)] == [
        RequestStatus.PENDING_REVIEW,
        RequestStatus.CREATED,
    ]


def test_list_scope_and_cross_account_cancel_is_404(store):
    mine = store.create(ACTOR, make())
    theirs = store.create(OTHER, make(purpose="social"))
    assert [row.id for row in store.list_own(ACTOR)] == [mine.id]
    assert [row.id for row in store.list_own(OTHER)] == [theirs.id]
    denied(ErrorCode.NOT_FOUND, lambda: store.cancel(ACTOR, theirs.id, 1))
    denied(ErrorCode.NOT_FOUND, lambda: store.cancel(ACTOR, uuid4(), 1))
    assert store.list_own(OTHER)[0].id == theirs.id


def test_stale_revision_conflicts_then_exact_cancel_removes(store):
    row = store.create(ACTOR, make())
    denied(ErrorCode.CONFLICT, lambda: store.cancel(ACTOR, row.id, 2))
    assert store.cancel(ACTOR, row.id, 1) == row.id
    assert store.list_own(ACTOR) == []
    denied(ErrorCode.NOT_FOUND, lambda: store.cancel(ACTOR, row.id, 1))


def test_per_user_and_global_limits():
    store = DemoChannelsStore(clock=lambda: NOW, per_user_max=2, global_max=3)
    store.create(ACTOR, make())
    store.create(ACTOR, make())
    denied(ErrorCode.CONFLICT, lambda: store.create(ACTOR, make()))
    store.create(OTHER, make())
    denied(ErrorCode.UNAVAILABLE, lambda: store.create(uuid4(), make()))
    defaults = DemoChannelsStore()
    assert (defaults._per_user_max, defaults._global_max) == (20, 200)


def test_naive_clock_fails_closed():
    store = DemoChannelsStore(clock=lambda: NOW.replace(tzinfo=None))
    denied(ErrorCode.UNAVAILABLE, lambda: store.create(ACTOR, make()))
    assert store.list_own(ACTOR) == []


@pytest.mark.parametrize(
    "extra",
    [
        {"actor_id": "x"},
        {"owner_id": str(uuid4())},
        {"department_id": "d"},
        {"role": "admin"},
        {"title": "free text"},
        {"status": "APPROVED"},
        {"official_badge": True},
    ],
)
def test_client_identity_role_and_free_text_rejected(extra):
    with pytest.raises(ValidationError):
        DemoChannelRequestCreate(**body(**extra))


@pytest.mark.parametrize(
    "bad",
    [
        {"consent": False},
        {"consent": "true"},
        {"consent": 1},
        {"purpose": "dating"},
        {"requested_kind": "STAFF"},
        {"requested_kind": "free"},
    ],
)
def test_consent_and_enums_are_strict(bad):
    with pytest.raises(ValidationError):
        make(**bad)
    assert make().requested_kind is RequestedKind.FREE


def client(store=None, actor=ACTOR):
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    if store is not None:
        app.state.demo_channels = store
    if actor is not ...:
        app.dependency_overrides[get_actor] = lambda: actor
    return TestClient(app)


def test_default_unmounted_and_fail_closed_503(store):
    with TestClient(create_app(Settings(environment="test"))) as app:
        assert app.get(PATH).status_code == 404
    with client(store, actor=...) as app:  # actor dependency not injected
        response = app.get(PATH)
        assert response.status_code == 503
        assert response.headers["cache-control"] == "private, no-store"
    with client(None) as app:  # store not set on app.state
        response = app.get(PATH)
        assert response.status_code == 503
        assert response.headers["cache-control"] == "private, no-store"
    with client(store, actor=None) as app:
        assert app.get(PATH).status_code == 401


def test_http_create_list_cancel_and_no_store(store):
    with client(store) as app:
        created = app.post(PATH, json=body(requested_kind="OFFICIAL"))
        assert created.status_code == 201
        assert created.headers["cache-control"] == "private, no-store"
        data = created.json()["data"]
        assert data["status"] == "PENDING_REVIEW" and data["official_badge"] is False
        assert "owner_id" not in data
        listed = app.get(PATH)
        assert listed.headers["cache-control"] == "private, no-store"
        assert [item["id"] for item in listed.json()["data"]["items"]] == [data["id"]]
        stale = app.delete(f"{PATH}/{data['id']}", params={"revision": 2})
        assert stale.status_code == 409 and stale.headers["cache-control"] == "private, no-store"
        done = app.delete(f"{PATH}/{data['id']}", params={"revision": 1})
        assert done.status_code == 200 and done.json()["data"]["cancelled"] is True
        assert app.get(PATH).json()["data"]["items"] == []


def test_http_validation_and_cross_account_errors_are_private(store):
    foreign = store.create(OTHER, make())
    with client(store) as app:
        for bad in [body(role="admin"), body(consent=False), body(owner_id=str(OTHER))]:
            response = app.post(PATH, json=bad)
            assert response.status_code == 400
            assert response.headers["cache-control"] == "private, no-store"
        assert app.delete(f"{PATH}/not-a-uuid", params={"revision": 1}).status_code == 400
        assert app.delete(f"{PATH}/{foreign.id}").status_code == 400  # revision required
        response = app.delete(f"{PATH}/{foreign.id}", params={"revision": 1})
        assert response.status_code == 404
        assert response.headers["cache-control"] == "private, no-store"
        assert app.get(PATH).json()["data"]["items"] == []
    assert store.list_own(OTHER)[0].id == foreign.id
