"""FR-NOT-004 dormant acknowledgement module (DEMO process memory, no auth/DB claims)."""

import threading
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.notice_acknowledgements import service as service_module
from app.features.notice_acknowledgements.models import AckInput, AckRequestInput
from app.features.notice_acknowledgements.ports import Actor, NoticeAccess
from app.features.notice_acknowledgements.router import get_actor, router
from app.features.notice_acknowledgements.service import (
    DemoAckStore,
    NoticeAcknowledgementService,
)
from app.schemas.common import ErrorCode

OWNER = Actor(uuid4())
OTHER_OWNER = Actor(uuid4())
STUDENT = Actor(uuid4())
STUDENT2 = Actor(uuid4())
OUTSIDER = Actor(uuid4())
NOTICE = uuid4()
OTHER_NOTICE = uuid4()
KEY = "key-0000000000000001"
KEY2 = "key-0000000000000002"
AT = datetime(2026, 10, 30, tzinfo=UTC)


class FakePort:
    """Stands in for the authoritative campus notice ledger; read on every call."""

    def __init__(self):
        self.notices = {
            NOTICE: NoticeAccess(OWNER.user_id, frozenset({STUDENT.user_id, STUDENT2.user_id}), 2),
            OTHER_NOTICE: NoticeAccess(OTHER_OWNER.user_id, frozenset({STUDENT.user_id}), 1),
        }
        self.calls = 0

    def resolve(self, notice_id: UUID):
        self.calls += 1
        return self.notices.get(notice_id)

    def set_audience(self, notice_id, members):
        old = self.notices[notice_id]
        self.notices[notice_id] = NoticeAccess(old.owner_id, frozenset(members), len(members))


@pytest.fixture
def ctx():
    port = FakePort()
    store = DemoAckStore()
    return port, store, NoticeAcknowledgementService(port, store, clock=lambda: AT)


def code(fn):
    with pytest.raises(ApiError) as error:
        fn()
    return error.value.code


def open_request(service, revision=None, key=KEY):
    body = AckRequestInput(notice_id=NOTICE, opt_in=True, revision=revision)
    return service.request(OWNER, body, key)


def test_opt_in_false_and_extra_authority_fields_are_rejected():
    for bad in (
        {"notice_id": str(NOTICE), "opt_in": False},
        {"notice_id": str(NOTICE), "opt_in": "true"},
        {"notice_id": str(NOTICE)},
        {"notice_id": str(NOTICE), "opt_in": True, "owner_id": str(OWNER.user_id)},
        {"notice_id": str(NOTICE), "opt_in": True, "audience": []},
        {"notice_id": str(NOTICE), "opt_in": True, "revision": -1},
        {"notice_id": str(NOTICE), "opt_in": True, "revision": "1"},
    ):
        with pytest.raises(ValidationError):
            AckRequestInput.model_validate(bad)
    with pytest.raises(ValidationError):
        AckInput.model_validate({"request_revision": True})


def test_owner_request_member_ack_and_summary_counts_only(ctx):
    port, _, service = ctx
    view = open_request(service)
    assert view.request_revision == 1 and view.official_effect is False
    assert view.storage == "PROCESS_MEMORY" and view.restart_reset is True
    state = service.state(STUDENT, NOTICE)
    assert state.requested and state.can_acknowledge and not state.can_view_summary
    receipt = service.acknowledge(STUDENT, NOTICE, AckInput(request_revision=1), KEY)
    assert receipt.acknowledged_at == AT
    assert service.state(STUDENT, NOTICE).acknowledged
    summary = service.summary(OWNER, NOTICE)
    assert (summary.eligible_total, summary.acknowledged_count) == (2, 1)
    dumped = summary.model_dump_json()
    assert str(STUDENT.user_id) not in dumped and str(OWNER.user_id) not in dumped
    assert port.calls >= 4


def test_no_request_means_no_ack_and_no_summary(ctx):
    _, store, service = ctx
    assert service.state(STUDENT, NOTICE).requested is False
    assert (
        code(lambda: service.acknowledge(STUDENT, NOTICE, AckInput(request_revision=1), KEY))
        == ErrorCode.NOT_FOUND
    )
    assert code(lambda: service.summary(OWNER, NOTICE)) == ErrorCode.NOT_FOUND
    assert store.requests == {} and store.acks == {}


def test_cross_owner_and_non_owner_cannot_request_or_aggregate(ctx):
    _, store, service = ctx
    body = AckRequestInput(notice_id=OTHER_NOTICE, opt_in=True)
    assert code(lambda: service.request(OWNER, body, KEY)) == ErrorCode.NOT_FOUND
    assert code(lambda: service.request(STUDENT, body, KEY)) == ErrorCode.FORBIDDEN
    open_request(service)
    assert code(lambda: service.summary(OTHER_OWNER, NOTICE)) == ErrorCode.NOT_FOUND
    assert code(lambda: service.summary(STUDENT, NOTICE)) == ErrorCode.FORBIDDEN
    assert code(lambda: service.state(OUTSIDER, NOTICE)) == ErrorCode.NOT_FOUND
    assert code(lambda: service.state(STUDENT, uuid4())) == ErrorCode.NOT_FOUND
    assert OTHER_NOTICE not in store.requests


def test_owner_not_in_audience_cannot_ack(ctx):
    _, _, service = ctx
    open_request(service)
    assert (
        code(lambda: service.acknowledge(OWNER, NOTICE, AckInput(request_revision=1), KEY))
        == ErrorCode.FORBIDDEN
    )


def test_current_audience_revocation_and_owner_transfer_apply_immediately(ctx):
    port, _, service = ctx
    open_request(service)
    service.acknowledge(STUDENT, NOTICE, AckInput(request_revision=1), KEY)
    port.set_audience(NOTICE, {STUDENT2.user_id})
    assert code(lambda: service.state(STUDENT, NOTICE)) == ErrorCode.NOT_FOUND
    assert (
        code(lambda: service.acknowledge(STUDENT, NOTICE, AckInput(request_revision=1), KEY))
        == ErrorCode.NOT_FOUND
    )
    summary = service.summary(OWNER, NOTICE)
    assert (summary.eligible_total, summary.acknowledged_count) == (1, 0)
    port.notices[NOTICE] = NoticeAccess(OTHER_OWNER.user_id, frozenset(), 0)
    assert code(lambda: service.summary(OWNER, NOTICE)) == ErrorCode.NOT_FOUND
    assert service.summary(OTHER_OWNER, NOTICE).eligible_total == 0


def test_untrusted_port_shape_fails_closed(ctx, monkeypatch):
    port, _, service = ctx
    port.notices[NOTICE] = NoticeAccess(OWNER.user_id, frozenset({STUDENT.user_id}), 5)
    assert code(lambda: service.state(OWNER, NOTICE)) == ErrorCode.UNAVAILABLE
    monkeypatch.setattr(service_module, "MAX_AUDIENCE", 1)
    port.set_audience(NOTICE, {STUDENT.user_id, STUDENT2.user_id})
    assert code(lambda: service.state(OWNER, NOTICE)) == ErrorCode.UNAVAILABLE


def test_request_cas_revision(ctx):
    _, _, service = ctx
    assert code(lambda: open_request(service, revision=1)) == ErrorCode.CONFLICT
    assert open_request(service, revision=0).request_revision == 1
    assert code(lambda: open_request(service, revision=0, key=KEY2)) == ErrorCode.CONFLICT
    assert open_request(service, revision=1, key=KEY2).request_revision == 1
    assert open_request(service, key="key-0000000000000003").request_revision == 1


def test_ack_cas_against_current_request_revision(ctx):
    _, store, service = ctx
    open_request(service)
    assert (
        code(lambda: service.acknowledge(STUDENT, NOTICE, AckInput(request_revision=2), KEY))
        == ErrorCode.CONFLICT
    )
    assert store.acks == {} and store.claims.keys() == {(OWNER.user_id, "request", NOTICE, KEY)}


def test_idempotency_replay_and_body_conflict(ctx):
    _, store, service = ctx
    first = open_request(service)
    assert open_request(service) == first
    assert code(lambda: open_request(service, revision=1)) == ErrorCode.CONFLICT
    a = service.acknowledge(STUDENT, NOTICE, AckInput(request_revision=1), KEY)
    b = service.acknowledge(STUDENT, NOTICE, AckInput(request_revision=1), KEY)
    c = service.acknowledge(STUDENT, NOTICE, AckInput(request_revision=1), KEY2)
    assert a == b == c and store.ack_total == 1
    # Same key in another actor namespace is independent.
    service.acknowledge(STUDENT2, NOTICE, AckInput(request_revision=1), KEY)
    assert service.summary(OWNER, NOTICE).acknowledged_count == 2


def test_bounded_caps(ctx, monkeypatch):
    port, store, service = ctx
    monkeypatch.setattr(service_module, "MAX_REQUESTS", 1)
    open_request(service)
    port.notices[OTHER_NOTICE] = NoticeAccess(OWNER.user_id, frozenset(), 0)
    body = AckRequestInput(notice_id=OTHER_NOTICE, opt_in=True)
    assert code(lambda: service.request(OWNER, body, KEY2)) == ErrorCode.RATE_LIMITED
    monkeypatch.setattr(service_module, "MAX_ACKS", 0)
    assert (
        code(lambda: service.acknowledge(STUDENT, NOTICE, AckInput(request_revision=1), KEY))
        == ErrorCode.RATE_LIMITED
    )
    monkeypatch.setattr(service_module, "MAX_CLAIMS", len(store.claims))
    assert (
        code(lambda: service.acknowledge(STUDENT, NOTICE, AckInput(request_revision=1), KEY2))
        == ErrorCode.RATE_LIMITED
    )
    assert store.acks.get(NOTICE, {}) == {}


def test_concurrent_acks_and_requests_are_single_records(ctx):
    _, store, service = ctx
    barrier = threading.Barrier(16)
    results = []

    def run(i):
        barrier.wait()
        results.append(open_request(service, key=f"key-concurrent-{i:04d}"))

    threads = [threading.Thread(target=run, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert {r.request_revision for r in results} == {1} and len(store.requests) == 1
    barrier = threading.Barrier(16)

    def ack(i):
        barrier.wait()
        service.acknowledge(STUDENT, NOTICE, AckInput(request_revision=1), f"key-ack-{i:08d}")

    threads = [threading.Thread(target=ack, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert store.ack_total == 1 and service.summary(OWNER, NOTICE).acknowledged_count == 1


def make_app(service=None, actor=None):
    application = create_app(Settings(environment="test"))
    application.include_router(router, prefix="/api/v1")
    if service is not None:
        application.state.notice_acknowledgements = service
    if actor is not None:
        application.dependency_overrides[get_actor] = lambda: actor
    return application


def test_default_503_no_store_and_not_globally_mounted(ctx):
    base = f"/api/v1/notice-acknowledgements/{NOTICE}"
    for application in (make_app(), make_app(service=ctx[2]), make_app(actor=OWNER)):
        with TestClient(application) as client:
            response = client.get(base)
            assert response.status_code == 503
            assert response.headers["cache-control"] == "private, no-store"
    application = make_app(actor=OWNER)
    application.state.notice_acknowledgements = object()
    with TestClient(application) as client:
        assert client.get(base).status_code == 503
    paths = create_app(Settings(environment="test")).openapi()["paths"]
    assert not any("notice-acknowledgements" in p for p in paths)


OWN_STATE_WIRE_KEYS = {
    "record_source",
    "storage",
    "official_effect",
    "restart_reset",
    "notice_id",
    "requested",
    "request_revision",
    "can_request",
    "can_acknowledge",
    "acknowledged",
    "acknowledged_at",
    "can_view_summary",
}


def test_http_own_state_wire_shape_matches_frontend_guard(ctx):
    """Exact key set and types checked by isOwnState in apps/web (incl. can_request)."""
    _, _, service = ctx
    base = "/api/v1/notice-acknowledgements"

    def check(data):
        assert set(data) == OWN_STATE_WIRE_KEYS
        assert data["notice_id"] == str(NOTICE)
        for flag in (
            "requested",
            "can_request",
            "can_acknowledge",
            "acknowledged",
            "can_view_summary",
        ):
            assert type(data[flag]) is bool
        if data["requested"]:
            assert type(data["request_revision"]) is int and data["request_revision"] >= 1
        else:
            assert data["request_revision"] is None
        assert (data["record_source"], data["storage"]) == ("DEMO", "PROCESS_MEMORY")
        assert data["official_effect"] is False and data["restart_reset"] is True
        return data

    with TestClient(make_app(service, OWNER)) as owner:
        before = check(owner.get(f"{base}/{NOTICE}").json()["data"])
        assert before["requested"] is False
        owner.post(
            base + "/request",
            json={"notice_id": str(NOTICE), "opt_in": True},
            headers={"Idempotency-Key": KEY},
        )
        after = check(owner.get(f"{base}/{NOTICE}").json()["data"])
        assert after["requested"] is True and after["request_revision"] == 1
    with TestClient(make_app(service, STUDENT)) as student:
        response = student.get(f"{base}/{NOTICE}")
        assert response.headers["cache-control"] == "private, no-store"
        check(response.json()["data"])
        for person in (OWNER, STUDENT2):
            assert str(person.user_id) not in response.text


def test_http_flow_errors_no_store_and_no_identity_leak(ctx):
    _, store, service = ctx
    base = "/api/v1/notice-acknowledgements"
    with TestClient(make_app(service, OWNER)) as owner:
        bad = owner.post(
            base + "/request",
            json={"notice_id": str(NOTICE), "opt_in": False},
            headers={"Idempotency-Key": KEY},
        )
        assert bad.status_code == 400 and bad.headers["cache-control"] == "private, no-store"
        assert store.requests == {}
        assert (
            owner.post(
                base + "/request", json={"notice_id": str(NOTICE), "opt_in": True}
            ).status_code
            == 400
        )
        ok = owner.post(
            base + "/request",
            json={"notice_id": str(NOTICE), "opt_in": True},
            headers={"Idempotency-Key": KEY},
        )
        assert ok.status_code == 200 and ok.json()["data"]["request_revision"] == 1
        assert ok.headers["cache-control"] == "private, no-store"
    with TestClient(make_app(service, STUDENT)) as student:
        acked = student.post(
            f"{base}/{NOTICE}/ack", json={"request_revision": 1}, headers={"Idempotency-Key": KEY}
        )
        assert acked.status_code == 200 and acked.json()["data"]["acknowledged"] is True
        assert student.get(f"{base}/{NOTICE}").json()["data"]["acknowledged"] is True
        denied = student.get(f"{base}/{NOTICE}/summary")
        assert denied.status_code == 403 and denied.headers["cache-control"] == "private, no-store"
    with TestClient(make_app(service, OWNER)) as owner:
        summary = owner.get(f"{base}/{NOTICE}/summary")
        data = summary.json()["data"]
        assert (data["eligible_total"], data["acknowledged_count"]) == (2, 1)
        assert data["official_effect"] is False and data["record_source"] == "DEMO"
        for person in (OWNER, STUDENT, STUDENT2):
            assert str(person.user_id) not in summary.text


def test_internal_failure_is_safe_and_no_store(ctx, monkeypatch):
    _, _, service = ctx

    def boom(*_):
        raise RuntimeError("secret-notice-text")

    monkeypatch.setattr(service, "state", boom)
    with TestClient(make_app(service, STUDENT), raise_server_exceptions=False) as client:
        response = client.get(f"/api/v1/notice-acknowledgements/{NOTICE}")
        assert response.status_code == 500 and "secret" not in response.text
        assert response.headers["cache-control"] == "private, no-store"
