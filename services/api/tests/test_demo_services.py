"""Fictional demo-service ledger tests: synthetic UUIDs/keys, no DB, network, browser or seed."""

import os
from threading import Barrier, Thread
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.demo_services import service as service_module
from app.features.demo_services.models import (
    AdvanceInput,
    CreateInput,
    DemoActor,
    DemoKind,
    DemoScenario,
    DemoStatus,
)
from app.features.demo_services.router import get_demo_actor, router
from app.features.demo_services.service import DEMO_DOCUMENT, DemoServices
from app.schemas.common import ErrorCode

OWNER_A = UUID("00000000-0000-4000-8000-00000000000a")
OWNER_B = UUID("00000000-0000-4000-8000-00000000000b")
MISSING = UUID("00000000-0000-4000-8000-0000000000ff")
A, B = DemoActor(OWNER_A), DemoActor(OWNER_B)
BASE = "/api/v1/me/demo-services"
ITEM_FIELDS = {
    "id",
    "kind",
    "scenario",
    "status",
    "status_label",
    "title",
    "revision",
    "created_at",
    "updated_at",
    "outcome_text",
    "document_text",
    "source_kind",
    "persistence",
    "official_effect",
    "sensitive_content_collected",
}


def key(n: int) -> str:
    return f"demo-key-{n:08d}"


def body(kind=DemoKind.CERTIFICATE, scenario=DemoScenario.STANDARD):
    return CreateInput(kind=kind, scenario=scenario, consent=True)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    # Delete by key name only; values are never read.
    for name in [name for name in os.environ if name.startswith("DIT_API_")]:
        monkeypatch.delenv(name)


def build(service: DemoServices | None = None, actor: dict | None = None):
    application = create_app(Settings(environment="test"))
    application.include_router(router, prefix="/api/v1")
    if actor is not None:
        application.dependency_overrides[get_demo_actor] = lambda: actor["value"]
    if service is not None:
        application.state.demo_services = service
    return application


@pytest.fixture
def http():
    actor = {"value": A}
    with TestClient(build(DemoServices(), actor)) as client:
        yield client, actor


def post(client, path="", json=None, n=1, **headers):
    return client.post(f"{BASE}{path}", json=json, headers={"Idempotency-Key": key(n), **headers})


def create_json(kind="CERTIFICATE", scenario="STANDARD"):
    return {"kind": kind, "scenario": scenario, "consent": True}


def assert_private(response):
    assert response.headers["cache-control"] == "private, no-store"


def assert_error(exc, code):
    assert exc.value.code is code


# ---- direct service ----


@pytest.mark.parametrize("kind", list(DemoKind))
@pytest.mark.parametrize("scenario", list(DemoScenario))
def test_service_lifecycle_all_kinds(kind, scenario):
    service = DemoServices()
    created = service.create(A, body(kind, scenario), key(1))
    assert (created.status, created.revision) == (DemoStatus.REQUESTED, 1)
    assert created.outcome_text is None and created.document_text is None
    assert created.official_effect is False and created.sensitive_content_collected is False
    assert (created.source_kind, created.persistence) == ("DEMO", "PROCESS_MEMORY")
    middle = service.advance(A, created.id, AdvanceInput(revision=1), key(2))
    assert (middle.status, middle.revision) == (DemoStatus.IN_PROGRESS, 2)
    assert middle.outcome_text is None and middle.document_text is None
    done = service.advance(A, created.id, AdvanceInput(revision=2), key(3))
    assert (done.status, done.revision) == (DemoStatus.COMPLETED, 3)
    assert done.outcome_text == (
        ("기본 가상 예시" if scenario is DemoScenario.STANDARD else "추가 검토 가상 예시")
        + ": "
        + service_module.OUTCOMES[kind]
    )
    if kind is DemoKind.CERTIFICATE:
        assert done.document_text == DEMO_DOCUMENT
        assert "가상 학생" in DEMO_DOCUMENT and "직인" in DEMO_DOCUMENT
        assert "공식 효력이 없습니다" in DEMO_DOCUMENT
    else:
        assert done.document_text is None
    assert done.created_at == created.created_at and done.title == service_module.TITLES[kind]
    assert set(done.model_dump()) == ITEM_FIELDS
    with pytest.raises(ApiError) as terminal:
        service.advance(A, created.id, AdvanceInput(revision=3), key(4))
    assert_error(terminal, ErrorCode.CONFLICT)
    assert service.list(A).items == [done]


def test_service_owner_isolation_and_listing_order():
    service = DemoServices()
    first = service.create(A, body(DemoKind.TUITION), key(1))
    second = service.create(A, body(DemoKind.ADMISSION_RESULT), key(2))
    service.create(B, body(), key(1))  # same key, different owner scope
    assert [row.id for row in service.list(A).items] == [second.id, first.id]
    assert len(service.list(B).items) == 1
    for call in (
        lambda: service.advance(B, first.id, AdvanceInput(revision=1), key(9)),
        lambda: service.delete(B, first.id, 1),
        lambda: service.advance(A, MISSING, AdvanceInput(revision=1), key(9)),
        lambda: service.delete(A, MISSING, 1),
    ):
        with pytest.raises(ApiError) as exc:
            call()
        assert_error(exc, ErrorCode.NOT_FOUND)
    assert service.list(A).items[1].revision == 1


def test_service_idempotency_replay_and_conflict():
    service = DemoServices()
    created = service.create(A, body(), key(1))
    assert service.create(A, body(), key(1)) is created
    with pytest.raises(ApiError) as changed:
        service.create(A, body(DemoKind.TUITION), key(1))
    assert_error(changed, ErrorCode.CONFLICT)
    advanced = service.advance(A, created.id, AdvanceInput(revision=1), key(2))
    # Replay returns the original response even after the record moved on.
    service.advance(A, created.id, AdvanceInput(revision=2), key(3))
    assert service.advance(A, created.id, AdvanceInput(revision=1), key(2)) is advanced
    with pytest.raises(ApiError) as changed_advance:
        service.advance(A, created.id, AdvanceInput(revision=2), key(2))
    assert_error(changed_advance, ErrorCode.CONFLICT)
    assert len(service.list(A).items) == 1


def test_service_stale_revision_and_delete_tombstone():
    service = DemoServices()
    created = service.create(A, body(), key(1))
    with pytest.raises(ApiError) as stale:
        service.advance(A, created.id, AdvanceInput(revision=2), key(2))
    assert_error(stale, ErrorCode.CONFLICT)
    service.advance(A, created.id, AdvanceInput(revision=1), key(3))
    with pytest.raises(ApiError) as stale_delete:
        service.delete(A, created.id, 1)
    assert_error(stale_delete, ErrorCode.CONFLICT)
    deleted = service.delete(A, created.id, 2)
    assert (deleted.id, deleted.deleted) == (created.id, True)
    assert service.delete(A, created.id, 2) == deleted  # same revision replay
    two, one = AdvanceInput(revision=2), AdvanceInput(revision=1)
    for call, code in (
        (lambda: service.delete(A, created.id, 3), ErrorCode.CONFLICT),
        (lambda: service.advance(A, created.id, two, key(4)), ErrorCode.NOT_FOUND),
        (lambda: service.advance(A, created.id, one, key(3)), ErrorCode.NOT_FOUND),
        (lambda: service.create(A, body(), key(1)), ErrorCode.CONFLICT),  # no resurrection
        (lambda: service.delete(B, created.id, 2), ErrorCode.NOT_FOUND),
    ):
        with pytest.raises(ApiError) as exc:
            call()
        assert_error(exc, code)
    assert service.list(A).items == []


def test_service_rejects_unverified_actor_key_and_revision():
    service = DemoServices()
    for actor in (None, OWNER_A, DemoActor(str(OWNER_A))):
        with pytest.raises(ApiError) as exc:
            service.list(actor)
        assert_error(exc, ErrorCode.UNAVAILABLE)
    for bad in ("short", "x" * 101, "demo-key-0000000!", "demo-key-00000001\n", 12345678901234567):
        with pytest.raises(ApiError) as exc:
            service.create(A, body(), bad)
        assert_error(exc, ErrorCode.VALIDATION)
    created = service.create(A, body(), key(1))
    for bad in (0, True, "1", 2_147_483_648):
        with pytest.raises(ApiError) as exc:
            service.delete(A, created.id, bad)
        assert_error(exc, ErrorCode.VALIDATION)
    assert service.list(A).items == [created]


def test_models_strict_frozen_and_without_owner_or_pii_fields():
    for payload in (
        {"kind": "CERTIFICATE", "scenario": "STANDARD", "consent": False},
        {"kind": "CERTIFICATE", "scenario": "STANDARD", "consent": 1},
        {"kind": "CERTIFICATE", "scenario": "STANDARD", "consent": "true"},
        {"kind": "CERTIFICATE", "scenario": "STANDARD"},
        {"kind": "REAL_PAYMENT", "scenario": "STANDARD", "consent": True},
        {"kind": "CERTIFICATE", "scenario": "OFFICIAL", "consent": True},
        {**create_json(), "owner_id": str(OWNER_B)},
    ):
        with pytest.raises(ValidationError):
            CreateInput.model_validate(payload)
    for revision in (0, True, "1", 1.0, 2_147_483_648):
        with pytest.raises(ValidationError):
            AdvanceInput.model_validate({"revision": revision})
    item = DemoServices().create(A, body(), key(1))
    with pytest.raises(ValidationError):
        item.status = DemoStatus.COMPLETED
    dumped = item.model_dump_json()
    assert str(OWNER_A) not in dumped and "owner" not in dumped


def test_capacity_limits_include_tombstones(monkeypatch):
    monkeypatch.setattr(service_module, "MAX_OWNER_RECORDS", 2)
    monkeypatch.setattr(service_module, "MAX_RECORDS", 3)
    service = DemoServices()
    first = service.create(A, body(), key(1))
    service.create(A, body(), key(2))
    service.delete(A, first.id, 1)  # tombstone still counts
    with pytest.raises(ApiError) as owner_full:
        service.create(A, body(), key(3))
    assert_error(owner_full, ErrorCode.RATE_LIMITED)
    service.create(B, body(), key(1))
    with pytest.raises(ApiError) as global_full:
        service.create(B, body(), key(2))
    assert_error(global_full, ErrorCode.RATE_LIMITED)
    assert len(service.list(A).items) == 1  # rejected creates left nothing behind


def test_claim_limit_never_evicts_and_replay_still_works(monkeypatch):
    monkeypatch.setattr(service_module, "MAX_CLAIMS", 2)
    service = DemoServices()
    created = service.create(A, body(), key(1))
    advanced = service.advance(A, created.id, AdvanceInput(revision=1), key(2))
    for call in (
        lambda: service.create(A, body(), key(3)),
        lambda: service.advance(A, created.id, AdvanceInput(revision=2), key(4)),
        lambda: service.create(B, body(), key(1)),
    ):
        with pytest.raises(ApiError) as exc:
            call()
        assert_error(exc, ErrorCode.RATE_LIMITED)
    assert service.create(A, body(), key(1)) is created
    assert service.advance(A, created.id, AdvanceInput(revision=1), key(2)) is advanced
    assert service.list(A).items == [advanced]


def run_parallel(count, target):
    barrier = Barrier(count)
    results: list = []

    def worker(index):
        barrier.wait()
        try:
            results.append(target(index))
        except ApiError as exc:
            results.append(exc.code)

    threads = [Thread(target=worker, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not any(thread.is_alive() for thread in threads)
    return results


def test_concurrent_same_key_create_dedupes():
    service = DemoServices()
    results = run_parallel(16, lambda _: service.create(A, body(), key(1)))
    assert len({row.id for row in results}) == 1
    assert len(service.list(A).items) == 1


def test_concurrent_cas_advance_exactly_one_success():
    service = DemoServices()
    created = service.create(A, body(), key(1))
    results = run_parallel(
        16, lambda index: service.advance(A, created.id, AdvanceInput(revision=1), key(100 + index))
    )
    successes = [row for row in results if not isinstance(row, ErrorCode)]
    assert len(successes) == 1 and successes[0].revision == 2
    assert results.count(ErrorCode.CONFLICT) == 15
    assert service.list(A).items == successes


def test_restart_and_separate_instances_reset_data():
    first = DemoServices()
    first.create(A, body(), key(1))
    assert DemoServices().list(A).items == []  # new process / other worker: empty ledger


# ---- HTTP contract on an isolated test app ----


def test_http_lifecycle_and_envelope(http):
    client, _ = http
    created = post(client, json=create_json("CERTIFICATE"), n=1)
    assert created.status_code == 201
    assert_private(created)
    item = created.json()["data"]
    assert created.json()["resource_version"] == 1 and set(item) == ITEM_FIELDS
    assert item["official_effect"] is False and item["sensitive_content_collected"] is False
    path = f"/{item['id']}/advance"
    middle = post(client, path, {"revision": 1}, n=2)
    done = post(client, path, {"revision": 2}, n=3)
    assert middle.status_code == done.status_code == 200
    assert done.json()["data"]["status"] == "COMPLETED"
    assert done.json()["data"]["document_text"] == DEMO_DOCUMENT
    assert done.json()["resource_version"] == 3
    listing = client.get(BASE, params={"owner_id": str(OWNER_B)})
    assert listing.status_code == 200
    assert_private(listing)
    data = listing.json()["data"]
    assert {k: data[k] for k in ("source_kind", "persistence", "official_effect")} == {
        "source_kind": "DEMO",
        "persistence": "PROCESS_MEMORY",
        "official_effect": False,
    }
    assert [row["id"] for row in data["items"]] == [item["id"]]
    assert str(OWNER_A) not in listing.text and "owner" not in listing.text
    terminal = post(client, path, {"revision": 3}, n=4)
    assert terminal.status_code == 409
    assert_private(terminal)
    deleted = client.delete(f"{BASE}/{item['id']}", params={"revision": 3})
    assert deleted.status_code == 200
    assert deleted.json()["data"] == {"id": item["id"], "deleted": True}
    assert_private(deleted)
    assert client.delete(f"{BASE}/{item['id']}", params={"revision": 3}).status_code == 200
    assert client.delete(f"{BASE}/{item['id']}", params={"revision": 2}).status_code == 409
    assert post(client, path, {"revision": 3}, n=5).status_code == 404
    assert post(client, json=create_json("CERTIFICATE"), n=1).status_code == 409
    assert client.get(BASE).json()["data"]["items"] == []


def test_http_idempotent_replay_and_conflict(http):
    client, _ = http
    first = post(client, json=create_json("TUITION"), n=1)
    replay = post(client, json=create_json("TUITION"), n=1)
    assert replay.status_code == 201 and replay.json()["data"] == first.json()["data"]
    assert post(client, json=create_json("ADMISSION_RESULT"), n=1).status_code == 409
    path = f"/{first.json()['data']['id']}/advance"
    advanced = post(client, path, {"revision": 1}, n=2)
    again = post(client, path, {"revision": 1}, n=2)
    assert again.json()["data"] == advanced.json()["data"]
    assert post(client, path, {"revision": 2}, n=2).status_code == 409
    assert post(client, path, {"revision": 1}, n=3).status_code == 409  # stale
    assert len(client.get(BASE).json()["data"]["items"]) == 1


def test_http_cross_owner_is_not_found_and_owner_body_rejected(http):
    client, actor = http
    item = post(client, json=create_json("PROTECTED_COUNSEL"), n=1).json()["data"]
    actor["value"] = B
    for response in (
        post(client, f"/{item['id']}/advance", {"revision": 1}, n=2),
        client.delete(f"{BASE}/{item['id']}", params={"revision": 1}),
    ):
        assert response.status_code == 404
        assert_private(response)
    assert client.get(BASE).json()["data"]["items"] == []
    for payload in (
        {**create_json(), "owner_id": str(OWNER_A)},
        {**create_json(), "user_id": str(OWNER_A)},
    ):
        response = post(client, json=payload, n=3)
        assert response.status_code == 400 and str(OWNER_A) not in response.text
    owner_claim = {"revision": 1, "owner_id": str(OWNER_A)}
    advance_owner = post(client, f"/{item['id']}/advance", owner_claim, n=4)
    assert advance_owner.status_code == 400
    actor["value"] = A
    own = client.get(BASE).json()["data"]["items"]
    assert [(row["id"], row["revision"]) for row in own] == [(item["id"], 1)]


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "CERTIFICATE", "scenario": "STANDARD", "consent": False},
        {"kind": "CERTIFICATE", "scenario": "STANDARD", "consent": 1},
        {"kind": "CERTIFICATE", "scenario": "STANDARD"},
        {**create_json(), "student_name": "가상-비밀-이름"},
        {**create_json("TUITION"), "account_no": "가상-비밀-계좌"},
        {**create_json("PROTECTED_COUNSEL"), "detail": "가상-비밀-상담"},
        {"kind": "가상-비밀-종류", "scenario": "STANDARD", "consent": True},
        ["가상-비밀-배열"],
    ],
)
def test_http_strict_invalid_body_not_echoed(http, payload):
    client, _ = http
    response = post(client, json=payload, n=1)
    assert response.status_code == 400
    assert_private(response)
    assert response.json()["code"] == "VALIDATION" and "가상-비밀" not in response.text
    assert client.get(BASE).json()["data"]["items"] == []


def test_http_invalid_revision_key_path_and_malformed(http):
    client, _ = http
    item = post(client, json=create_json(), n=1).json()["data"]
    path = f"/{item['id']}/advance"
    for revision in (0, True, "1", 1.5, None):
        assert post(client, path, {"revision": revision}, n=2).status_code == 400
    bad_keys = ({"Idempotency-Key": "short"}, {"Idempotency-Key": "bad key with spaces!!"}, {})
    for headers in bad_keys:
        response = client.post(BASE, json=create_json(), headers=headers)
        assert response.status_code == 400
        assert_private(response)
    no_key = client.post(f"{BASE}{path}", json={"revision": 1})
    assert no_key.status_code == 400
    for query in ({}, {"revision": 0}, {"revision": "x"}):
        response = client.delete(f"{BASE}/{item['id']}", params=query)
        assert response.status_code == 400
        assert_private(response)
    malformed = client.post(
        BASE,
        content=b'{"kind": "CERT',
        headers={"Idempotency-Key": key(3), "Content-Type": "application/json"},
    )
    assert malformed.status_code == 400
    assert_private(malformed)
    bad_id = post(client, "/not-a-uuid/advance", {"revision": 1}, n=4)
    assert bad_id.status_code == 400
    assert_private(bad_id)
    unknown = client.get(f"{BASE}/{item['id']}/unknown-route")
    assert unknown.status_code in (404, 405)
    assert_private(unknown)
    assert client.get(BASE).json()["data"]["items"][0]["revision"] == 1


def test_http_capacity_returns_429(monkeypatch, http):
    monkeypatch.setattr(service_module, "MAX_OWNER_RECORDS", 1)
    client, _ = http
    assert post(client, json=create_json(), n=1).status_code == 201
    full = post(client, json=create_json(), n=2)
    assert full.status_code == 429 and full.json()["retryable"] is True
    assert_private(full)


def test_http_unconfigured_actor_or_service_is_503():
    for application in (
        build(DemoServices()),  # default actor dependency
        build(None, {"value": A}),  # no app.state service
    ):
        with TestClient(application) as client:
            for response in (
                client.get(BASE),
                post(client, json=create_json(), n=1),
                post(client, f"/{MISSING}/advance", {"revision": 1}, n=2),
                client.delete(f"{BASE}/{MISSING}", params={"revision": 1}),
            ):
                assert response.status_code == 503
                assert_private(response)
    wrong = build(None, {"value": A})
    wrong.state.demo_services = object()
    with TestClient(wrong) as client:
        assert client.get(BASE).status_code == 503


def test_http_restart_resets_data():
    actor = {"value": A}
    with TestClient(build(DemoServices(), actor)) as client:
        assert post(client, json=create_json(), n=1).status_code == 201
    with TestClient(build(DemoServices(), actor)) as client:
        assert client.get(BASE).json()["data"]["items"] == []


def test_router_is_dormant_in_app_factory():
    application = create_app(Settings(environment="test"))
    assert not any("demo-services" in path for path in application.openapi()["paths"])
    assert not hasattr(application.state, "demo_services")
    with TestClient(application) as client:
        response = client.get(BASE)
        assert response.status_code == 404
        assert_private(response)
