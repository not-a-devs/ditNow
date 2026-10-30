"""DEMO admin change proposals: fictional codes, PROCESS_MEMORY only, no approval/execution."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from itertools import count
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.factory import create_app
from app.features.admin_change_requests import service as service_module
from app.features.admin_change_requests.models import AdminChangeActor
from app.features.admin_change_requests.router import get_actor, router
from app.features.admin_change_requests.service import AdminChangeRequestService

NOW = datetime(2026, 10, 30, 2, 0, tzinfo=UTC)
OWNER, OTHER = uuid4(), uuid4()
BODY = {
    "target_code": "STUDENT_DEMO_A",
    "proposal_scope": "DEPARTMENT_STUDENT",
    "reason_code": "ACADEMIC_DEMO",
    "consent": True,
}
BASE = "/api/v1/admin-change-requests"


def key(n: int = 0) -> dict[str, str]:
    return {"Idempotency-Key": f"intent-key-{n:08d}"}


class Harness:
    def __init__(self, *, mount_service=True, override_actor=True):
        self.actor: AdminChangeActor | None = AdminChangeActor(OWNER, True)
        ids = count(1)
        self.service = AdminChangeRequestService(
            clock=lambda: NOW, id_factory=lambda: str(UUID(int=next(ids), version=4))
        )
        app = create_app(Settings(environment="test"))
        app.include_router(router, prefix="/api/v1")
        if mount_service:
            app.state.admin_change_requests = self.service
        if override_actor:
            app.dependency_overrides[get_actor] = lambda: self.actor
        self.client = TestClient(app)

    def as_actor(self, user_id: UUID, can_manage: bool = True):
        self.actor = AdminChangeActor(user_id, can_manage)

    def create(self, n=0, body=BODY):
        return self.client.post(BASE, json=body, headers=key(n))


@pytest.fixture
def h():
    return Harness()


def no_store(response):
    assert response.headers["Cache-Control"] == "private, no-store"
    return response


def test_not_mounted_in_default_app():
    paths = create_app(Settings(environment="test")).openapi()["paths"]
    assert not any("admin-change-requests" in path for path in paths)


@pytest.mark.parametrize(
    "harness",
    [
        {"mount_service": False, "override_actor": True},
        {"mount_service": True, "override_actor": False},
        {"mount_service": False, "override_actor": False},
    ],
)
def test_default_dependencies_fail_closed_503_with_no_store(harness):
    h = Harness(**harness)
    for response in (
        h.client.get(BASE),
        h.create(),
        h.client.post(f"{BASE}/{uuid4()}/submit", json={"expected_revision": 1}, headers=key()),
        h.client.delete(f"{BASE}/{uuid4()}", params={"revision": 1}),
    ):
        assert no_store(response).status_code == 503
        assert response.json()["code"] == "UNAVAILABLE"
    assert h.service._rows == {}


def test_wrong_object_on_app_state_is_503():
    h = Harness(mount_service=False)
    h.client.app.state.admin_change_requests = object()
    assert no_store(h.client.get(BASE)).status_code == 503


def test_full_lifecycle_has_demo_markers_and_no_owner(h):
    created = no_store(h.create())
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["state"] == "DRAFT" and data["revision"] == 1
    assert data["record_source"] == "DEMO" and data["storage"] == "PROCESS_MEMORY"
    assert data["official_effect"] is False and data["restart_reset"] is True
    assert str(OWNER) not in created.text and "owner" not in created.text
    pid = data["id"]

    submitted = no_store(
        h.client.post(f"{BASE}/{pid}/submit", json={"expected_revision": 1}, headers=key(1))
    )
    assert submitted.status_code == 200
    assert submitted.json()["data"]["state"] == "SUBMITTED"
    assert submitted.json()["data"]["revision"] == 2

    withdrawn = no_store(h.client.delete(f"{BASE}/{pid}", params={"revision": 2}))
    assert withdrawn.json()["data"]["state"] == "WITHDRAWN"
    assert withdrawn.json()["data"]["withdrawn_at"] is not None

    listed = no_store(h.client.get(BASE)).json()["data"]
    assert [item["state"] for item in listed["items"]] == ["WITHDRAWN"]  # tombstone kept
    assert listed["items"][0]["revision"] == 3
    assert listed["official_effect"] is False and str(OWNER) not in str(listed)


def test_draft_can_be_withdrawn_directly(h):
    pid = h.create().json()["data"]["id"]
    response = h.client.delete(f"{BASE}/{pid}", params={"revision": 1})
    assert response.status_code == 200 and response.json()["data"]["state"] == "WITHDRAWN"


def test_no_approval_or_execution_routes(h):
    pid = h.create().json()["data"]["id"]
    for suffix in ("approve", "execute", "apply"):
        response = h.client.post(f"{BASE}/{pid}/{suffix}", json={}, headers=key(9))
        assert response.status_code in (404, 405)
    assert not any(
        word in path
        for path in h.client.app.openapi()["paths"]
        for word in ("approve", "execute", "grant")
    )


@pytest.mark.parametrize(
    "body",
    [
        {**BODY, "consent": False},
        {k: v for k, v in BODY.items() if k != "consent"},
        {**BODY, "consent": "true"},
        {**BODY, "consent": 1},
        {**BODY, "target_code": "REAL_USER"},
        {**BODY, "target_code": str(uuid4())},
        {**BODY, "proposal_scope": "ADMIN"},
        {**BODY, "reason_code": "free text"},
        {**BODY, "owner_id": str(OTHER)},
        {**BODY, "role": "ADMIN"},
        {**BODY, "state": "SUBMITTED"},
        {**BODY, "note": "personal info"},
    ],
)
def test_create_rejects_non_fixed_or_extra_fields(h, body):
    response = no_store(h.create(body=body))
    assert response.status_code == 400 and response.json()["code"] == "VALIDATION"
    assert h.service._rows == {}


@pytest.mark.parametrize(
    ("target", "scope", "reason"),
    [
        ("STUDENT_DEMO_A", "DEPARTMENT_STUDENT", "ACADEMIC_DEMO"),
        ("STUDENT_DEMO_B", "YEAR_STUDENT", "CORRECTION_DEMO"),
    ],
)
def test_plain_json_enum_strings_are_accepted(h, target, scope, reason):
    body = {"target_code": target, "proposal_scope": scope, "reason_code": reason, "consent": True}
    response = no_store(h.client.post(BASE, json=body, headers=key(11)))
    assert response.status_code == 201
    data = response.json()["data"]
    assert (data["target_code"], data["proposal_scope"], data["reason_code"]) == (
        target,
        scope,
        reason,
    )
    assert data["state"] == "DRAFT" and data["revision"] == 1


@pytest.mark.parametrize("consent", [1, 0, False, "true", "True", None, [True]])
def test_consent_must_be_json_true_with_otherwise_valid_enums(h, consent):
    response = no_store(h.create(body={**BODY, "consent": consent}))
    assert response.status_code == 400 and response.json()["code"] == "VALIDATION"
    assert h.service._rows == {}
    # Same enum payload with consent=true succeeds, so the enums were not the cause.
    assert h.create(n=1).status_code == 201


def test_fixed_revisions_and_timestamps():
    ticks = iter([NOW.replace(minute=m) for m in range(10)])
    h = Harness()
    h.service.clock = lambda: next(ticks)
    a = h.create(n=1).json()["data"]
    assert (a["state"], a["revision"]) == ("DRAFT", 1)
    assert (
        a["created_at"] == a["updated_at"]
        and a["submitted_at"] is None
        and a["withdrawn_at"] is None
    )
    s = h.client.post(f"{BASE}/{a['id']}/submit", json={"expected_revision": 1}, headers=key(2))
    s = s.json()["data"]
    assert (s["state"], s["revision"]) == ("SUBMITTED", 2)
    assert (
        s["created_at"] == a["created_at"]
        and s["submitted_at"] == s["updated_at"] > a["created_at"]
    )
    w = h.client.delete(f"{BASE}/{a['id']}", params={"revision": 2}).json()["data"]
    assert (w["state"], w["revision"]) == ("WITHDRAWN", 3)
    assert (
        w["submitted_at"] == s["submitted_at"]
        and w["withdrawn_at"] == w["updated_at"] > s["updated_at"]
    )
    b = h.create(n=3).json()["data"]
    d = h.client.delete(f"{BASE}/{b['id']}", params={"revision": 1}).json()["data"]
    assert (d["state"], d["revision"], d["submitted_at"]) == ("WITHDRAWN", 2, None)
    assert d["withdrawn_at"] == d["updated_at"] > d["created_at"] == b["created_at"]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Idempotency-Key": "short"},
        {"Idempotency-Key": "x" * 101},
        {"Idempotency-Key": "bad key with space"},
    ],
)
def test_create_requires_valid_idempotency_key(h, headers):
    response = no_store(h.client.post(BASE, json=BODY, headers=headers))
    assert response.status_code == 400
    assert h.service._rows == {}


def test_server_sets_owner_and_client_owner_is_ignored(h):
    h.create()
    (row,) = h.service._rows.values()
    assert row.owner_id == OWNER


def test_cross_owner_is_404_for_submit_and_withdraw_and_hidden_in_list(h):
    pid = h.create().json()["data"]["id"]
    h.as_actor(OTHER)
    assert h.client.get(BASE).json()["data"]["items"] == []
    foreign_submit = h.client.post(
        f"{BASE}/{pid}/submit", json={"expected_revision": 1}, headers=key(2)
    )
    foreign_delete = h.client.delete(f"{BASE}/{pid}", params={"revision": 1})
    unknown = h.client.delete(f"{BASE}/{uuid4()}", params={"revision": 1})
    for response in (foreign_submit, foreign_delete, unknown):
        assert no_store(response).status_code == 404
    assert foreign_submit.json()["message"] == unknown.json()["message"]
    assert h.service._rows[pid].state == "DRAFT" and h.service._rows[pid].revision == 1


def test_idempotency_key_is_scoped_per_owner(h):
    h.create(n=5)
    h.as_actor(OTHER)
    response = h.create(n=5)
    assert response.status_code == 201 and response.json()["data"]["replayed"] is False
    assert len(h.service._rows) == 2


def test_current_permission_checked_on_every_read_and_write(h):
    pid = h.create().json()["data"]["id"]
    h.as_actor(OWNER, False)  # permission revoked after create
    for response in (
        h.client.get(BASE),
        h.create(n=7),
        h.create(n=0),  # even a replay of an earlier receipt is refused
        h.client.post(f"{BASE}/{pid}/submit", json={"expected_revision": 1}, headers=key(1)),
        h.client.delete(f"{BASE}/{pid}", params={"revision": 1}),
    ):
        assert no_store(response).status_code == 403
        assert str(pid) not in response.text
    assert len(h.service._rows) == 1 and h.service._rows[pid].state == "DRAFT"


def test_unauthenticated_actor_is_401(h):
    h.actor = None
    assert no_store(h.client.get(BASE)).status_code == 401
    assert no_store(h.create()).status_code == 401


def test_create_replay_returns_receipt_and_conflicting_reuse_is_409(h):
    first = h.create(n=3).json()["data"]
    again = h.create(n=3).json()["data"]
    assert again["id"] == first["id"] and again["replayed"] is True
    assert len(h.service._rows) == 1
    changed = h.create(n=3, body={**BODY, "target_code": "STUDENT_DEMO_B"})
    assert changed.status_code == 409 and len(h.service._rows) == 1


def test_submit_replay_after_success_returns_original_receipt(h):
    pid = h.create().json()["data"]["id"]
    url = f"{BASE}/{pid}/submit"
    first = h.client.post(url, json={"expected_revision": 1}, headers=key(4))
    replay = h.client.post(url, json={"expected_revision": 1}, headers=key(4))
    assert first.json()["data"]["revision"] == 2
    assert replay.status_code == 200 and replay.json()["data"]["replayed"] is True
    assert replay.json()["data"]["revision"] == 2
    other_pid = h.create(n=1).json()["data"]["id"]
    reused = h.client.post(
        f"{BASE}/{other_pid}/submit", json={"expected_revision": 1}, headers=key(4)
    )
    assert reused.status_code == 409


def test_cas_conflicts(h):
    pid = h.create().json()["data"]["id"]
    url = f"{BASE}/{pid}/submit"
    assert h.client.post(url, json={"expected_revision": 2}, headers=key(1)).status_code == 409
    assert h.client.post(url, json={"expected_revision": 1}, headers=key(2)).status_code == 200
    # already SUBMITTED: a new intent cannot re-submit
    assert h.client.post(url, json={"expected_revision": 2}, headers=key(3)).status_code == 409
    assert h.client.delete(f"{BASE}/{pid}", params={"revision": 1}).status_code == 409
    assert h.client.delete(f"{BASE}/{pid}", params={"revision": 2}).status_code == 200
    assert h.client.delete(f"{BASE}/{pid}", params={"revision": 3}).status_code == 409
    assert h.client.post(url, json={"expected_revision": 3}, headers=key(5)).status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"expected_revision": "1"},
        {"expected_revision": 0},
        {"expected_revision": True},
        {"expected_revision": 1, "state": "APPROVED"},
        {},
    ],
)
def test_submit_body_is_strict(h, body):
    pid = h.create().json()["data"]["id"]
    response = h.client.post(f"{BASE}/{pid}/submit", json=body, headers=key(1))
    assert no_store(response).status_code == 400
    assert h.service._rows[pid].state == "DRAFT"


def test_path_and_query_are_validated(h):
    assert h.client.delete(f"{BASE}/not-a-uuid", params={"revision": 1}).status_code == 400
    pid = h.create().json()["data"]["id"]
    assert h.client.delete(f"{BASE}/{pid}").status_code == 400
    assert h.client.delete(f"{BASE}/{pid}", params={"revision": 0}).status_code == 400


def test_concurrent_submit_has_single_winner(h):
    pid = h.create().json()["data"]["id"]

    def attempt(n):
        return h.client.post(
            f"{BASE}/{pid}/submit", json={"expected_revision": 1}, headers=key(100 + n)
        ).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(16)))
    assert results.count(200) == 1 and results.count(409) == 15
    assert h.service._rows[pid].revision == 2


def test_concurrent_same_key_create_makes_one_record(h):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: h.create(n=42).json()["data"]["id"], range(12)))
    assert len(set(results)) == 1 and len(h.service._rows) == 1


def test_owner_cap_counts_tombstones(h, monkeypatch):
    monkeypatch.setattr(service_module, "OWNER_CAP", 2)
    first = h.create(n=1).json()["data"]
    h.client.delete(f"{BASE}/{first['id']}", params={"revision": 1})
    assert h.create(n=2).status_code == 201
    capped = no_store(h.create(n=3))
    assert capped.status_code == 429 and len(h.service._rows) == 2
    h.as_actor(OTHER)
    assert h.create(n=3).status_code == 201


def test_key_cap(h, monkeypatch):
    monkeypatch.setattr(service_module, "OWNER_KEY_CAP", 1)
    assert h.create(n=1).status_code == 201
    assert h.create(n=1).status_code == 201  # replay does not need room
    assert h.create(n=2).status_code == 429


def test_restart_resets_memory():
    first = Harness()
    first.create()
    assert len(first.client.get(BASE).json()["data"]["items"]) == 1
    assert Harness().client.get(BASE).json()["data"]["items"] == []


def test_naive_clock_is_unavailable():
    h = Harness()
    h.service.clock = lambda: datetime(2026, 10, 30)
    assert no_store(h.create()).status_code == 503
    assert h.service._rows == {}


def test_unexpected_error_is_safe_500_with_no_store(h, monkeypatch):
    def boom(*_):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(h.service, "list_own", boom)
    response = no_store(h.client.get(BASE))
    assert response.status_code == 500 and "secret detail" not in response.text
