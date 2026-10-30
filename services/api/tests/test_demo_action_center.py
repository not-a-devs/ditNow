"""DEMO action center: fixed synthetic process-memory content, never MariaDB or real records."""

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.demo_action_center import DemoActionCenterStore, get_actor, get_store, router
from app.features.demo_action_center.store import CARDS
from app.schemas.common import ErrorCode

BASE = "/api/v1/me/demo-action-center"
ACTOR, OTHER = uuid4(), uuid4()


def build(actor=ACTOR, store: DemoActionCenterStore | None = None, *, install=True):
    application = create_app(Settings(environment="test"))
    application.include_router(router, prefix="/api/v1")
    if install:
        application.state.demo_action_center = store or DemoActionCenterStore()
    if actor is not ...:
        application.dependency_overrides[get_actor] = lambda: actor
    return application


def client(**kwargs) -> TestClient:
    return TestClient(build(**kwargs))


def read(api: TestClient, notification_id, revision=1):
    return api.post(f"{BASE}/notifications/{notification_id}/read", json={"revision": revision})


def test_router_is_not_mounted_by_default():
    paths = create_app(Settings(environment="test")).openapi()["paths"]
    assert not any("demo-action-center" in path for path in paths)


def test_defaults_fail_closed_with_no_store():
    # No actor override: the default dependency is 503, not a fallback identity.
    response = client(actor=...).get(f"{BASE}/summary")
    assert response.status_code == 503
    assert response.json()["code"] == "UNAVAILABLE"
    assert response.headers["Cache-Control"] == "private, no-store"
    # Actor present but no store installed on app.state.
    response = client(install=False).get(f"{BASE}/summary")
    assert response.status_code == 503
    assert response.headers["Cache-Control"] == "private, no-store"


def test_missing_actor_is_unauthorized():
    response = client(actor=None).get(f"{BASE}/summary")
    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "private, no-store"


def test_wrong_store_type_is_unavailable():
    application = build(install=False)
    application.state.demo_action_center = object()
    assert TestClient(application).get(f"{BASE}/summary").status_code == 503


def test_summary_is_fixed_fictional_and_rule_based():
    response = client().get(f"{BASE}/summary")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    data = response.json()["data"]
    assert data["mode"] == "DEMO"
    assert data["storage"] == "PROCESS_MEMORY"
    assert data["rule_based"] is True
    assert data["ai_generated"] is False
    assert data["school_connection"] == "NOT_CONNECTED"
    assert [c["id"] for c in data["cards"]] == ["demo-class-1", "demo-task-1", "demo-notice-1"]
    assert [c["kind"] for c in data["cards"]] == ["CLASS", "TASK", "NOTICE"]
    assert all(c["record_source"] == "DEMO" for c in data["cards"])
    assert all(c["title"].startswith("[DEMO]") for c in data["cards"])
    assert len(data["notifications"]) == 3
    assert data["unread_count"] == 3
    assert {n["link"] for n in data["notifications"]} <= {"/app/classrooms", "/app/department"}
    assert all(c["link"].startswith("/app/") for c in data["cards"])
    assert all(n["delivery"] == "IN_APP_ONLY" and n["revision"] == 1 for n in data["notifications"])


def test_ids_are_stable_per_owner_and_never_leak_owner():
    store = DemoActionCenterStore()
    mine, theirs = client(store=store), client(actor=OTHER, store=store)
    first = mine.get(f"{BASE}/summary").json()["data"]["notifications"]
    again = mine.get(f"{BASE}/summary").json()["data"]["notifications"]
    other = theirs.get(f"{BASE}/summary").json()["data"]["notifications"]
    assert [n["id"] for n in first] == [n["id"] for n in again]
    assert not {n["id"] for n in first} & {n["id"] for n in other}
    body = mine.get(f"{BASE}/summary").text
    assert str(ACTOR) not in body and ACTOR.hex not in body
    assert str(OTHER) not in theirs.get(f"{BASE}/summary").text


def test_read_is_owner_scoped_cas_and_idempotent():
    store = DemoActionCenterStore()
    mine, theirs = client(store=store), client(actor=OTHER, store=store)
    target = mine.get(f"{BASE}/summary").json()["data"]["notifications"][0]["id"]
    theirs.get(f"{BASE}/summary")

    # Other owner and unknown IDs are the same 404.
    assert read(theirs, target).status_code == 404
    assert read(mine, uuid4()).status_code == 404
    # Stale revision conflicts without changing state.
    conflict = read(mine, target, revision=2)
    assert conflict.status_code == 409
    assert conflict.headers["Cache-Control"] == "private, no-store"

    done = read(mine, target)
    assert done.status_code == 200
    data = done.json()["data"]
    assert data["already_read"] is False
    assert data["notification"]["read"] is True
    assert data["notification"]["revision"] == 2
    assert data["unread_count"] == 2
    assert done.json()["resource_version"] == 2

    # Replays (any revision) never double count or bump the revision.
    for revision in (1, 2, 99):
        replay = read(mine, target, revision=revision).json()["data"]
        assert replay["already_read"] is True
        assert replay["notification"]["revision"] == 2
        assert replay["unread_count"] == 2

    assert mine.get(f"{BASE}/summary").json()["data"]["unread_count"] == 2
    assert theirs.get(f"{BASE}/summary").json()["data"]["unread_count"] == 3


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"revision": "1"},
        {"revision": 0},
        {"revision": True},
        {"revision": 1, "actor_id": str(OTHER)},
        {"revision": 1, "department_id": str(uuid4())},
        {"revision": 1, "role": "ADMIN"},
    ],
)
def test_read_rejects_invalid_or_identity_fields(body):
    api = client()
    target = api.get(f"{BASE}/summary").json()["data"]["notifications"][0]["id"]
    response = api.post(f"{BASE}/notifications/{target}/read", json=body)
    assert response.status_code == 400
    assert response.headers["Cache-Control"] == "private, no-store"
    assert api.get(f"{BASE}/summary").json()["data"]["unread_count"] == 3


def test_non_uuid_path_is_validation_error():
    response = client().post(f"{BASE}/notifications/{ACTOR.hex[:8]}/read", json={"revision": 1})
    assert response.status_code == 400


def test_identity_headers_and_query_are_ignored():
    store = DemoActionCenterStore()
    api = client(store=store)
    theirs = client(actor=OTHER, store=store)
    target = theirs.get(f"{BASE}/summary").json()["data"]["notifications"][0]["id"]
    response = api.post(
        f"{BASE}/notifications/{target}/read?actor_id={OTHER}",
        json={"revision": 1},
        headers={"X-Actor-Id": str(OTHER), "X-Role": "ADMIN"},
    )
    assert response.status_code == 404


def test_owner_capacity_fails_closed():
    store = DemoActionCenterStore(max_owners=2)
    store.summary(uuid4())
    store.summary(uuid4())
    with pytest.raises(ApiError) as caught:
        store.summary(uuid4())
    assert caught.value.code == ErrorCode.UNAVAILABLE
    assert client(store=store).get(f"{BASE}/summary").status_code == 503


def test_id_collision_with_owner_fails_closed():
    owner = uuid4()
    store = DemoActionCenterStore(id_factory=lambda: owner)
    with pytest.raises(ApiError) as caught:
        store.summary(owner)
    assert caught.value.code == ErrorCode.INTERNAL


def test_reset_clears_process_memory():
    store = DemoActionCenterStore()
    before = store.summary(ACTOR)
    store.mark_read(ACTOR, before.notifications[0].id, 1)
    store.reset()
    after = store.summary(ACTOR)
    assert after.unread_count == 3
    assert {n.id for n in after.notifications}.isdisjoint({n.id for n in before.notifications})
    with pytest.raises(ApiError):
        store.mark_read(ACTOR, before.notifications[0].id, 1)


def test_concurrent_reads_count_once():
    store = DemoActionCenterStore()
    target: UUID = store.summary(ACTOR).notifications[1].id
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.mark_read(ACTOR, target, 1), range(16)))
    assert sum(not r.already_read for r in results) == 1
    assert store.summary(ACTOR).unread_count == 2
    assert store.summary(ACTOR).notifications[1].revision == 2


def test_returned_views_do_not_alias_store_state():
    store = DemoActionCenterStore()
    view = store.summary(ACTOR)
    view.notifications[0].read = True
    view.cards[0].title = "변조"
    view.cards.clear()
    fresh = store.summary(ACTOR)
    assert fresh.unread_count == 3
    assert len(fresh.cards) == len(CARDS) == 3
    assert fresh.cards[0].title == CARDS[0].title == "[DEMO] 가상 자료구조 수업"


def test_get_store_direct_default():
    class State:
        pass

    class App:
        state = State()

    class Req:
        app = App()

    with pytest.raises(ApiError) as caught:
        get_store(Req())  # type: ignore[arg-type]
    assert caught.value.code == ErrorCode.UNAVAILABLE
