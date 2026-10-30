"""DEMO attendance sandbox: fail-closed dependencies, self-only state, code bounds, no-store.

In-process TestClient only; PROCESS_MEMORY adapter, no DB and no real attendance ledger.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.factory import create_app
from app.features.demo_attendance import (
    DEMO_CODE,
    MAX_OWNERS,
    STATE_ATTR,
    DemoAttendanceFull,
    DemoAttendanceStore,
    get_actor,
    router,
)

BASE = "/api/v1/me/demo-attendance"
USER_A = UUID("00000000-0000-4000-8000-0000000000a1")
USER_B = UUID("00000000-0000-4000-8000-0000000000b2")
NOW = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)


class ActorHolder:
    def __init__(self, actor: UUID | None) -> None:
        self.actor = actor

    def __call__(self) -> UUID | None:
        return self.actor


def make_client(
    *, actor: ActorHolder | None = None, store: DemoAttendanceStore | None = None
) -> TestClient:
    application = create_app(Settings(environment="test"))
    application.include_router(router, prefix="/api/v1")
    if actor is not None:
        application.dependency_overrides[get_actor] = actor
    if store is not None:
        setattr(application.state, STATE_ATTR, store)
    return TestClient(application, raise_server_exceptions=False)


def assert_no_store(response) -> None:
    assert response.headers["cache-control"] == "private, no-store"


@pytest.fixture
def holder() -> ActorHolder:
    return ActorHolder(USER_A)


@pytest.fixture
def client(holder: ActorHolder) -> TestClient:
    return make_client(actor=holder, store=DemoAttendanceStore(clock=lambda: NOW))


# ------------------------------------------------------------ fail-closed dependencies


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [("GET", "/card", None), ("GET", "/state", None), ("POST", "/check-in", {"code": DEMO_CODE})],
)
def test_default_actor_dependency_fails_closed_503(method, path, body):
    response = make_client(store=DemoAttendanceStore()).request(method, BASE + path, json=body)
    assert response.status_code == 503
    assert response.json()["code"] == "UNAVAILABLE"
    assert_no_store(response)


def test_missing_store_fails_closed_503():
    response = make_client(actor=ActorHolder(USER_A)).get(BASE + "/state")
    assert response.status_code == 503
    assert_no_store(response)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [("GET", "/card", None), ("GET", "/state", None), ("POST", "/check-in", {"code": DEMO_CODE})],
)
def test_unauthenticated_actor_is_401_and_records_nothing(method, path, body):
    store = DemoAttendanceStore()
    response = make_client(actor=ActorHolder(None), store=store).request(
        method, BASE + path, json=body
    )
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert_no_store(response)
    assert store.owner_count() == 0


def test_non_uuid_actor_is_rejected():
    store = DemoAttendanceStore()
    holder = ActorHolder(None)
    holder.actor = "00000000-0000-4000-8000-0000000000a1"  # type: ignore[assignment]
    response = make_client(actor=holder, store=store).get(BASE + "/state")
    assert response.status_code == 401


# ------------------------------------------------------------ card


def test_card_is_synthetic_demo_without_credentials(client):
    response = client.get(BASE + "/card")
    assert response.status_code == 200
    assert_no_store(response)
    data = response.json()["data"]
    card, session = data["card"], data["session"]
    assert card["mode"] == "DEMO"
    assert card["storage"] == "PROCESS_MEMORY"
    assert card["valid_credential"] is False
    assert card["qr_enabled"] is False
    assert "DEMO" in card["display_alias"]
    assert session["simulation_code"] == DEMO_CODE
    assert session["method"] == "NUMERIC_CODE_SIMULATION"
    assert str(USER_A) not in response.text


# ------------------------------------------------------------ check-in and state


def test_check_in_then_replay_keeps_first_timestamp(client):
    assert client.get(BASE + "/state").json()["data"]["checked_in"] is False

    first = client.post(BASE + "/check-in", json={"code": DEMO_CODE})
    assert first.status_code == 201
    assert_no_store(first)
    assert first.json()["data"]["replayed"] is False

    again = client.post(BASE + "/check-in", json={"code": DEMO_CODE})
    assert again.status_code == 200
    assert again.json()["data"]["replayed"] is True
    assert again.json()["data"]["checked_in_at"] == first.json()["data"]["checked_in_at"]

    state = client.get(BASE + "/state").json()["data"]
    assert state["checked_in"] is True
    assert state["checked_in_at"] == first.json()["data"]["checked_in_at"]
    assert str(USER_A) not in first.text


def test_accounts_are_isolated(client, holder):
    assert client.post(BASE + "/check-in", json={"code": DEMO_CODE}).status_code == 201

    holder.actor = USER_B
    state_b = client.get(BASE + "/state")
    assert state_b.json()["data"] == {
        "mode": "DEMO",
        "storage": "PROCESS_MEMORY",
        "method": "NUMERIC_CODE_SIMULATION",
        "checked_in": False,
        "checked_in_at": None,
    }
    assert client.post(BASE + "/check-in", json={"code": DEMO_CODE}).status_code == 201

    holder.actor = USER_A
    assert client.post(BASE + "/check-in", json={"code": DEMO_CODE}).json()["data"]["replayed"]


def test_wrong_code_is_422_and_records_nothing(client):
    response = client.post(BASE + "/check-in", json={"code": "654321"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION"
    assert_no_store(response)
    assert client.get(BASE + "/state").json()["data"]["checked_in"] is False


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"code": ""},
        {"code": "12345"},
        {"code": "1234567"},
        {"code": "12345a"},
        {"code": " 123456"},
        {"code": "１２３４５６"},
        {"code": 123456},
        {"code": "1" * 10_000},
        {"code": DEMO_CODE, "user_id": str(USER_B)},
        {"code": DEMO_CODE, "department": "CSE"},
        {"code": DEMO_CODE, "role": "PROFESSOR"},
    ],
)
def test_malformed_or_extra_body_is_400(client, body):
    response = client.post(BASE + "/check-in", json=body)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"
    assert_no_store(response)
    assert client.get(BASE + "/state").json()["data"]["checked_in"] is False


def test_caller_supplied_identity_query_is_ignored(client, holder):
    response = client.get(BASE + "/state", params={"user_id": str(USER_B)})
    assert response.status_code == 200
    client.post(BASE + "/check-in", json={"code": DEMO_CODE})
    holder.actor = USER_B
    assert client.get(BASE + "/state").json()["data"]["checked_in"] is False


# ------------------------------------------------------------ bounds and concurrency


def test_store_capacity_is_bounded_and_full_is_503():
    store = DemoAttendanceStore(max_owners=2)
    holder = ActorHolder(UUID(int=1))
    client = make_client(actor=holder, store=store)
    for value in (1, 2):
        holder.actor = UUID(int=value)
        assert client.post(BASE + "/check-in", json={"code": DEMO_CODE}).status_code == 201
    holder.actor = UUID(int=3)
    full = client.post(BASE + "/check-in", json={"code": DEMO_CODE})
    assert full.status_code == 503
    assert_no_store(full)
    holder.actor = UUID(int=1)
    assert client.post(BASE + "/check-in", json={"code": DEMO_CODE}).status_code == 200
    assert store.owner_count() == 2


def test_store_rejects_capacity_beyond_200():
    with pytest.raises(ValueError):
        DemoAttendanceStore(max_owners=MAX_OWNERS + 1)
    with pytest.raises(ValueError):
        DemoAttendanceStore(max_owners=0)


def test_default_store_stops_at_200_owners():
    store = DemoAttendanceStore()
    for value in range(MAX_OWNERS):
        store.check_in(UUID(int=value + 1))
    with pytest.raises(DemoAttendanceFull):
        store.check_in(UUID(int=10_000))
    assert store.owner_count() == MAX_OWNERS


def test_concurrent_check_ins_record_once():
    store = DemoAttendanceStore()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.check_in(USER_A), range(32)))
    assert sum(created for _, created in results) == 1
    assert len({record.checked_in_at for record, _ in results}) == 1
    assert store.owner_count() == 1


def test_reads_do_not_create_owner_entries(client):
    client.get(BASE + "/card")
    client.get(BASE + "/state")
    store = client.app.state.demo_attendance
    assert store.owner_count() == 0
