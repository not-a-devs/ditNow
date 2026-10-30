"""Root wiring of fictional process-memory demos to the common current context.

Fake ``get_context`` overrides are TEST ONLY and stand in for the real session/binding check; no
DB, engine, bootstrap, credential, network or role grant is used. This is not a real DB test.
"""

import asyncio
import importlib
import os
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.v1.auth import Credentials
from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.integrations.demo_runtime import DEMO_ROUTER_MODULES, demo_owner
from app.integrations.platform_runtime.dependencies import (
    RequestContext,
    get_context,
    get_runtime,
)
from app.schemas.common import ErrorCode

# Explicit router submodules: the package __init__ re-exports the APIRouter as ``router``.
services = importlib.import_module("app.features.demo_services.router")
attendance = importlib.import_module("app.features.demo_attendance.router")
profile = importlib.import_module("app.features.demo_profile.router")
action_center = importlib.import_module("app.features.demo_action_center.router")
channels = importlib.import_module("app.features.demo_channels.router")

API = "/api/v1"
SERVICES = f"{API}/me/demo-services"
ATTENDANCE = f"{API}/me/demo-attendance"
PROFILE = f"{API}/me/demo-profile"
CHANNELS = f"{API}/me/demo-channels"
ACTION = f"{API}/me/demo-action-center"
OWNER_A = UUID("00000000-0000-4000-8000-00000000000a")
OWNER_B = UUID("00000000-0000-4000-8000-00000000000b")
STATE_ATTRS = (
    "demo_services",
    "demo_attendance",
    "demo_profile",
    "demo_action_center",
    "demo_channels",
)
ACTOR_MODULES = {
    "services": services,
    "attendance": attendance,
    "profile": profile,
    "action_center": action_center,
    "channels": channels,
}
SPOOF = {"X-User-Id": str(OWNER_B), "X-Role": "admin", "X-Student-Id": "20260000"}
TRAVEL = {
    "previous_ends_at": "2026-10-30T10:00:00+09:00",
    "next_starts_at": "2026-10-30T10:15:00+09:00",
    "estimated_travel_minutes": 10,
}
SERVICE_BODY = {"kind": "CERTIFICATE", "scenario": "STANDARD", "consent": True}


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    # Delete by key name only; values are never read.
    for name in [name for name in os.environ if name.startswith("DIT_API_")]:
        monkeypatch.delenv(name)

    def no_engine(*_args, **_kwargs):
        raise AssertionError("demo integration must not create a database engine")

    monkeypatch.setattr("app.factory.create_database_engine", no_engine)


def enabled_app() -> FastAPI:
    # P0 flag only: no schema attestation, DB settings or approval ids, so no runtime/engine.
    return create_app(Settings(environment="test", p0_runtime_enabled=True))


def with_fake_context(application: FastAPI, sessions: dict[str, UUID]) -> FastAPI:
    """TEST ONLY: token -> current approved binding; missing/revoked tokens are rejected."""

    async def fake_context(creds: Credentials) -> RequestContext:
        token = creds.credentials if creds else None
        owner = sessions.get(token) if token else None
        if owner is None:
            raise ApiError(ErrorCode.UNAUTHORIZED)
        binding = SimpleNamespace(principal=SimpleNamespace(user_id=owner, active=True))
        return RequestContext(None, token, binding)  # type: ignore[arg-type]

    application.dependency_overrides[get_context] = fake_context
    return application


def bearer(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def assert_private(response) -> None:
    assert response.headers["cache-control"] == "private, no-store"


def assert_error(response, status: int, code: ErrorCode) -> None:
    assert response.status_code == status
    assert response.json()["code"] == code.value
    assert_private(response)


def plain_get_paths(module) -> list[str]:
    return [
        f"{API}{route.path}"
        for route in module.router.routes
        if isinstance(route, APIRoute) and "GET" in route.methods and "{" not in route.path
    ]


def create_service(client: TestClient, token: str, n: int):
    return client.post(
        SERVICES,
        json=SERVICE_BODY,
        headers=bearer(token, **{"Idempotency-Key": f"integration-key-{n:06d}"}),
    )


def test_default_app_mounts_public_routes_only():
    application = create_app(Settings(environment="test"))
    paths = application.openapi()["paths"]
    assert f"{API}/data-provenance" in paths
    assert f"{API}/campus-travel/calculate" in paths
    assert not any("/me/demo-" in path for path in paths)
    for attr in STATE_ATTRS:
        assert not hasattr(application.state, attr)
    assert application.dependency_overrides == {}
    with TestClient(application) as client:
        assert client.get(SERVICES, headers=SPOOF).status_code == 404
        assert client.get(f"{ATTENDANCE}/state", headers=SPOOF).status_code == 404
        provenance = client.get(f"{API}/data-provenance")
        travel = client.post(f"{API}/campus-travel/calculate", json=TRAVEL)
        invalid = client.post(
            f"{API}/campus-travel/calculate", json={**TRAVEL, "student_id": "private"}
        )
    assert provenance.status_code == 200 and provenance.json()["data"]
    assert travel.status_code == 200
    assert travel.json()["data"]["remaining_seconds"] == 300
    assert travel.json()["data"]["estimate_source"] == "USER_INPUT"
    assert_error(invalid, 400, ErrorCode.VALIDATION)
    for response in (provenance, travel):
        assert_private(response)


def test_enabled_without_runtime_fails_closed_through_common_context():
    application = enabled_app()
    assert application.state.platform_runtime is None
    assert application.state.assistant.engine is None
    for attr in STATE_ATTRS:
        assert getattr(application.state, attr) is not None
    # Only the fictional actor placeholders are overridden; canonical auth stays in place.
    assert get_context not in application.dependency_overrides
    assert get_runtime not in application.dependency_overrides
    assert set(application.dependency_overrides) == {
        services.get_demo_actor,
        attendance.get_actor,
        profile.get_actor,
        action_center.get_actor,
        channels.get_actor,
    }
    spoofed = bearer("not-a-session", **SPOOF)
    with TestClient(application) as client:
        for module in ACTOR_MODULES.values():
            for path in plain_get_paths(module):
                assert_error(client.get(path, headers=spoofed), 503, ErrorCode.UNAVAILABLE)
                assert_error(
                    client.get(path, params={"user_id": str(OWNER_A)}),
                    503,
                    ErrorCode.UNAVAILABLE,
                )
        assert_error(create_service(client, "not-a-session", 1), 503, ErrorCode.UNAVAILABLE)
        check_in = client.post(f"{ATTENDANCE}/check-in", json={"code": "123456"}, headers=spoofed)
        assert_error(check_in, 503, ErrorCode.UNAVAILABLE)
        # Public metadata and manual calculation stay available alongside the closed demos.
        assert client.get(f"{API}/data-provenance").status_code == 200
        assert client.post(f"{API}/campus-travel/calculate", json=TRAVEL).status_code == 200


def test_each_module_actor_resolves_current_context_owner():
    application = with_fake_context(enabled_app(), {"token-a": OWNER_A, "token-b": OWNER_B})

    # Probe routes reuse each module's own placeholder so the root override is exercised.
    for name, module in ACTOR_MODULES.items():
        placeholder = getattr(module, "get_demo_actor", None) or module.get_actor
        actor_dependency = Depends(placeholder)

        def probe(actor=actor_dependency) -> dict[str, str]:
            return {"owner": str(getattr(actor, "user_id", actor))}

        application.add_api_route(f"/probe/{name}", probe, methods=["GET"])

    with TestClient(application) as client:
        for name in ACTOR_MODULES:
            a = client.get(f"/probe/{name}", headers=bearer("token-a", **SPOOF))
            b = client.get(f"/probe/{name}", headers=bearer("token-b"))
            assert a.json() == {"owner": str(OWNER_A)}
            assert b.json() == {"owner": str(OWNER_B)}
            assert client.get(f"/probe/{name}").status_code == 401
        for module in ACTOR_MODULES.values():
            for path in plain_get_paths(module):
                assert_error(client.get(path, headers=SPOOF), 401, ErrorCode.UNAUTHORIZED)


def test_demo_services_and_attendance_are_owner_isolated():
    application = with_fake_context(enabled_app(), {"token-a": OWNER_A, "token-b": OWNER_B})
    with TestClient(application) as client:
        created = create_service(client, "token-a", 1)
        assert created.status_code == 201
        assert_private(created)
        item_id = created.json()["data"]["id"]

        b_list = client.get(SERVICES, headers=bearer("token-b", **{"X-User-Id": str(OWNER_A)}))
        assert b_list.status_code == 200 and b_list.json()["data"]["items"] == []
        b_delete = client.delete(
            f"{SERVICES}/{item_id}", params={"revision": 1}, headers=bearer("token-b")
        )
        assert b_delete.status_code >= 400
        assert_private(b_delete)
        a_list = client.get(SERVICES, headers=bearer("token-a"))
        assert [item["id"] for item in a_list.json()["data"]["items"]] == [item_id]

        check_in = client.post(
            f"{ATTENDANCE}/check-in", json={"code": "123456"}, headers=bearer("token-a")
        )
        assert check_in.status_code == 201
        assert_private(check_in)
        a_state = client.get(f"{ATTENDANCE}/state", headers=bearer("token-a"))
        b_state = client.get(f"{ATTENDANCE}/state", headers=bearer("token-b", **SPOOF))
        assert a_state.json()["data"]["checked_in"] is True
        assert b_state.json()["data"]["checked_in"] is False
        wrong = client.post(
            f"{ATTENDANCE}/check-in", json={"code": "000000"}, headers=bearer("token-b")
        )
        assert wrong.status_code == 422
        assert_private(wrong)


def test_switched_or_revoked_context_is_denied():
    sessions = {"token-1": OWNER_A}
    application = with_fake_context(enabled_app(), sessions)
    with TestClient(application) as client:
        assert create_service(client, "token-1", 1).status_code == 201
        assert (
            client.post(
                f"{ATTENDANCE}/check-in", json={"code": "123456"}, headers=bearer("token-1")
            ).status_code
            == 201
        )

        # Current binding changed for the same token: the old owner's data is not reachable.
        sessions["token-1"] = OWNER_B
        switched = client.get(SERVICES, headers=bearer("token-1"))
        assert switched.status_code == 200 and switched.json()["data"]["items"] == []
        state = client.get(f"{ATTENDANCE}/state", headers=bearer("token-1"))
        assert state.json()["data"]["checked_in"] is False

        del sessions["token-1"]
        for response in (
            client.get(SERVICES, headers=bearer("token-1", **SPOOF)),
            client.get(f"{ATTENDANCE}/state", headers=bearer("token-1")),
            create_service(client, "token-1", 2),
        ):
            assert_error(response, 401, ErrorCode.UNAUTHORIZED)


def test_memory_stores_are_owned_per_application():
    first = with_fake_context(enabled_app(), {"token-a": OWNER_A})
    second = with_fake_context(enabled_app(), {"token-a": OWNER_A})
    for attr in STATE_ATTRS:
        assert getattr(first.state, attr) is not getattr(second.state, attr)
    with TestClient(first) as one, TestClient(second) as two:
        assert create_service(one, "token-a", 1).status_code == 201
        assert (
            one.post(
                f"{ATTENDANCE}/check-in", json={"code": "123456"}, headers=bearer("token-a")
            ).status_code
            == 201
        )
        assert len(one.get(SERVICES, headers=bearer("token-a")).json()["data"]["items"]) == 1
        assert two.get(SERVICES, headers=bearer("token-a")).json()["data"]["items"] == []
        state = two.get(f"{ATTENDANCE}/state", headers=bearer("token-a"))
        assert state.json()["data"]["checked_in"] is False


def test_runtime_binds_router_submodules_not_reexported_routers():
    for name, module in ACTOR_MODULES.items():
        assert module.__name__ == DEMO_ROUTER_MODULES[name]
        placeholder = "get_demo_actor" if name == "services" else "get_actor"
        assert isinstance(module.router, APIRouter) and callable(getattr(module, placeholder))


def test_profile_is_owner_isolated_for_current_context():
    application = with_fake_context(enabled_app(), {"token-a": OWNER_A, "token-b": OWNER_B})
    update = {"interests": ["coding"], "skill_level": "intermediate", "revision": 1}
    with TestClient(application) as client:
        a_before = client.get(PROFILE, headers=bearer("token-a"))
        assert a_before.status_code == 200 and a_before.json()["data"]["revision"] == 1
        assert_private(a_before)
        # Spoofed headers name B; the current context still decides the owner (A).
        a_patch = client.patch(PROFILE, json=update, headers=bearer("token-a", **SPOOF))
        assert a_patch.status_code == 200 and a_patch.json()["data"]["revision"] == 2
        assert_private(a_patch)
        b_view = client.get(PROFILE, headers=bearer("token-b")).json()["data"]
        assert b_view["interests"] == [] and b_view["revision"] == 1
        a_view = client.get(PROFILE, headers=bearer("token-a")).json()["data"]
        assert a_view["interests"] == ["coding"] and a_view["revision"] == 2
        spoofed_body = {**update, "user_id": str(OWNER_A)}
        assert_error(
            client.patch(PROFILE, json=spoofed_body, headers=bearer("token-b")),
            400,
            ErrorCode.VALIDATION,
        )
        assert_error(client.patch(PROFILE, json=update), 401, ErrorCode.UNAUTHORIZED)
        assert client.get(PROFILE, headers=bearer("token-b")).json()["data"]["revision"] == 1


def test_channels_are_owner_isolated_for_current_context():
    application = with_fake_context(enabled_app(), {"token-a": OWNER_A, "token-b": OWNER_B})
    body = {"purpose": "study", "requested_kind": "FREE", "consent": True}
    with TestClient(application) as client:
        created = client.post(CHANNELS, json=body, headers=bearer("token-a", **SPOOF))
        assert created.status_code == 201
        assert_private(created)
        item_id = created.json()["data"]["id"]
        b_list = client.get(CHANNELS, headers=bearer("token-b", **{"X-User-Id": str(OWNER_A)}))
        assert b_list.status_code == 200 and b_list.json()["data"]["items"] == []
        b_cancel = client.delete(
            f"{CHANNELS}/{item_id}", params={"revision": 1}, headers=bearer("token-b")
        )
        assert b_cancel.status_code >= 400
        assert_private(b_cancel)
        a_items = client.get(CHANNELS, headers=bearer("token-a")).json()["data"]["items"]
        assert [item["id"] for item in a_items] == [item_id]
        spoofed_body = {**body, "owner_id": str(OWNER_B)}
        assert_error(
            client.post(CHANNELS, json=spoofed_body, headers=bearer("token-b")),
            400,
            ErrorCode.VALIDATION,
        )
        assert_error(client.post(CHANNELS, json=body), 401, ErrorCode.UNAUTHORIZED)
        assert client.get(CHANNELS, headers=bearer("token-b")).json()["data"]["items"] == []


def test_action_center_is_owner_isolated_for_current_context():
    application = with_fake_context(enabled_app(), {"token-a": OWNER_A, "token-b": OWNER_B})
    with TestClient(application) as client:
        a_summary = client.get(f"{ACTION}/summary", headers=bearer("token-a"))
        b_summary = client.get(f"{ACTION}/summary", headers=bearer("token-b", **SPOOF))
        assert a_summary.status_code == 200 and b_summary.status_code == 200
        assert_private(a_summary)
        a_ids = [item["id"] for item in a_summary.json()["data"]["notifications"]]
        b_ids = [item["id"] for item in b_summary.json()["data"]["notifications"]]
        assert a_ids and b_ids and not set(a_ids) & set(b_ids)

        # B cannot read A's notification; unknown and other-owner IDs look identical.
        foreign = client.post(
            f"{ACTION}/notifications/{a_ids[0]}/read",
            json={"revision": 1},
            headers=bearer("token-b", **{"X-User-Id": str(OWNER_A)}),
        )
        assert_error(foreign, 404, ErrorCode.NOT_FOUND)
        own = client.post(
            f"{ACTION}/notifications/{a_ids[0]}/read",
            json={"revision": 1},
            headers=bearer("token-a"),
        )
        assert own.status_code == 200 and own.json()["data"]["unread_count"] == 2
        assert_private(own)
        anonymous = client.post(f"{ACTION}/notifications/{a_ids[1]}/read", json={"revision": 1})
        assert_error(anonymous, 401, ErrorCode.UNAUTHORIZED)
        b_after = client.get(f"{ACTION}/summary", headers=bearer("token-b")).json()["data"]
        assert b_after["unread_count"] == 3
        a_after = client.get(f"{ACTION}/summary", headers=bearer("token-a")).json()["data"]
        assert a_after["unread_count"] == 2


def test_demo_owner_reads_only_current_binding_principal():
    ctx = RequestContext(
        None,  # type: ignore[arg-type]
        "token",
        SimpleNamespace(principal=SimpleNamespace(user_id=OWNER_B, active=True)),  # type: ignore[arg-type]
    )
    assert asyncio.run(demo_owner(ctx)) == OWNER_B
