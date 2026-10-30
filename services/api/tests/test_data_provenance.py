"""HTTP and catalog tests for the public provenance explanation (FR-ADM-004, TC-V1-ADM-004).

Fixed in-process catalog only; no DB, auth provider, network or model is involved.
"""

import json
import re

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from app.core.config import Settings
from app.core.errors import (
    ApiError,
    api_error_handler,
    http_error_handler,
    validation_error_handler,
)
from app.core.logging import SafeRequestMiddleware
from app.factory import create_app
from app.features.data_provenance import (
    PROVENANCE_LABELS,
    DataProvenanceDependencies,
    ProvenanceCatalog,
    create_data_provenance_router,
    fixed_catalog,
    router,
)

API = "/api/v1"
ERROR_KEYS = {"code", "message", "field_errors", "retryable", "request_id"}
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def mount(feature_router) -> TestClient:
    # TEST ONLY: feature injection must not be shadowed by factory's lazy public router includes.
    application = FastAPI()
    application.add_exception_handler(ApiError, api_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(HTTPException, http_error_handler)
    application.add_middleware(SafeRequestMiddleware)
    application.include_router(feature_router, prefix=API)
    return TestClient(application, raise_server_exceptions=False)


@pytest.fixture
def client() -> TestClient:
    return mount(create_data_provenance_router())


def provide(catalog: ProvenanceCatalog):
    def dependency() -> ProvenanceCatalog:
        return catalog

    return dependency


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    assert set(response.json()) == ERROR_KEYS
    assert response.json()["code"] == code
    assert response.headers["Cache-Control"] == "private, no-store"


def test_overview_returns_four_fixed_labels_and_explicit_status(client) -> None:
    response = client.get(f"{API}/data-provenance")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    body = response.json()
    assert set(body) == {"data", "resource_version", "server_time"}
    data = body["data"]
    assert [item["label"] for item in data["labels"]] == list(PROVENANCE_LABELS)
    assert data["status"] == {
        "school_sso_connected": False,
        "financial_effect": "NONE",
        "persistence": "IN_PROCESS_FIXED",
        "content_administration": "NOT_IMPLEMENTED",
    }
    assert data["feature_ids"] == ["FR-ADM-004"]
    for item in data["labels"]:
        assert set(item) == {"label", "title", "description", "user_guidance"}
        assert item["title"] and item["description"] and item["user_guidance"]


@pytest.mark.parametrize("label", PROVENANCE_LABELS)
def test_each_label_is_individually_readable(client, label) -> None:
    response = client.get(f"{API}/data-provenance/labels/{label}")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.json()["data"]["label"] == label


@pytest.mark.parametrize("label", ["demo", "OFFICIAL", "ADMIN", "UNKNOWN1"])
def test_unknown_label_is_rejected_with_common_envelope(client, label) -> None:
    assert_error(client.get(f"{API}/data-provenance/labels/{label}"), 400, "VALIDATION")


@pytest.mark.parametrize(
    "query",
    ["url=https://example.invalid/", "source=http://127.0.0.1/", "label=DEMO", "role=admin"],
)
def test_any_query_parameter_is_rejected(client, query) -> None:
    assert_error(client.get(f"{API}/data-provenance?{query}"), 400, "VALIDATION")
    assert_error(client.get(f"{API}/data-provenance/labels/DEMO?{query}"), 400, "VALIDATION")


def test_client_supplied_identity_headers_do_not_change_content(client) -> None:
    plain = client.get(f"{API}/data-provenance").json()["data"]
    spoofed = client.get(
        f"{API}/data-provenance",
        headers={
            "X-Test-User": "user-a",
            "X-Actor-Id": "admin",
            "X-Department": "cs",
            "X-Role": "OPERATOR",
            "Authorization": "Bearer synthetic-not-a-token",
        },
    ).json()["data"]
    assert spoofed == plain


def test_read_only_methods_only(client) -> None:
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)(f"{API}/data-provenance").status_code == 405
    methods = {m for route in router.routes for m in route.methods}
    assert methods <= {"GET", "HEAD"}


def test_payload_has_no_uuid_urls_secrets_or_configuration(client) -> None:
    texts = [json.dumps(client.get(f"{API}/data-provenance").json(), ensure_ascii=False)]
    texts += [
        json.dumps(client.get(f"{API}/data-provenance/labels/{label}").json(), ensure_ascii=False)
        for label in PROVENANCE_LABELS
    ]
    for text in texts:
        assert not UUID.search(text)
        lowered = text.lower()
        for marker in ("http://", "https://", "secret", "password", "token", "dsn", "mariadb"):
            assert marker not in lowered


def test_incomplete_catalog_fails_closed_with_unavailable() -> None:
    complete = fixed_catalog().overview().labels
    broken = ProvenanceCatalog(labels=tuple(complete[:3]))
    deps = DataProvenanceDependencies(catalog=provide(broken))
    broken_client = mount(create_data_provenance_router(deps))
    assert_error(broken_client.get(f"{API}/data-provenance"), 503, "UNAVAILABLE")
    assert_error(broken_client.get(f"{API}/data-provenance/labels/DEMO"), 503, "UNAVAILABLE")


def test_reordered_or_duplicated_catalog_fails_closed() -> None:
    labels = fixed_catalog().overview().labels
    for candidate in (tuple(reversed(labels)), (labels[0], labels[0], labels[2], labels[3])):
        deps = DataProvenanceDependencies(catalog=provide(ProvenanceCatalog(candidate)))
        assert_error(
            mount(create_data_provenance_router(deps)).get(f"{API}/data-provenance"),
            503,
            "UNAVAILABLE",
        )


def test_catalog_dependency_failure_is_hidden_as_internal_error() -> None:
    def explode() -> ProvenanceCatalog:
        raise RuntimeError("synthetic failure with secret detail")

    response = mount(
        create_data_provenance_router(DataProvenanceDependencies(catalog=explode))
    ).get(f"{API}/data-provenance")
    assert_error(response, 500, "INTERNAL")
    assert "secret" not in response.text


def test_default_app_keeps_global_public_provenance_route() -> None:
    with TestClient(create_app(Settings(environment="test"))) as client:
        response = client.get(f"{API}/data-provenance")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"


def test_returned_models_are_copies_and_restart_is_identical() -> None:
    first = fixed_catalog()
    overview = first.overview()
    overview.labels[0].title = "변조"
    assert first.overview().labels[0].title != "변조"
    assert fixed_catalog().overview() == first.overview()
