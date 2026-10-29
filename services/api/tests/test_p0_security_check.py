"""HTTP MockTransport only. No listener, credentials file, DB, seed, or actual network."""

import json
from copy import deepcopy
from unittest.mock import Mock
from uuid import UUID

import httpx
import pytest

from scripts import verify_p0_security as check

IDS = {
    name: str(UUID(int=i + 1))
    for i, name in enumerate(("A", "B", "DA", "DB", "OP", "POST", "TEAM", "CHECK", "CLOSE"))
}
MARKER = "DITNOW_DEMO_P0_OPPORTUNITY"
PASSWORD = "FICTIONAL-password-only"


def environment():
    return {
        check.OPT_IN: "1",
        check.APPROVED: "1",
        "DIT_API_P0_CHECK_BASE_URL": "http://127.0.0.1:8000",
        "DIT_API_P0_CHECK_A_STUDENT_ID": "DITDEMO_A",
        "DIT_API_P0_CHECK_A_PASSWORD": PASSWORD,
        "DIT_API_P0_CHECK_B_STUDENT_ID": "DITDEMO_B",
        "DIT_API_P0_CHECK_B_PASSWORD": PASSWORD,
        "DIT_API_P0_CHECK_OPPORTUNITY_ID": IDS["OP"],
        "DIT_API_P0_CHECK_OPPORTUNITY_MARKER": MARKER,
    }


class Wire:
    """Deliberately small fake of the documented HTTP contract, not a production repository."""

    def __init__(self, fault=None):
        self.fault = fault
        self.tokens, self.rows, self.saved, self.claims = {}, {}, {}, {}
        self.calls = []
        self.count = 0
        self.a_logins = 0
        self.deleted_ids = []

    def response(self, data, status=200, *, replay=False):
        body = (
            {"data": data}
            if status < 400
            else {
                "code": {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT"}[
                    status
                ],
                "message": "safe-error",
            }
        )
        headers = {"cache-control": "private, no-store"}
        if replay:
            headers["Idempotent-Replayed"] = "true"
        return httpx.Response(status, json=body, headers=headers)

    def me(self, who):
        return {
            "user_id": IDS[who],
            "display_name": "Fictional " + who,
            "record_source": "DEMO",
            "department_id": IDS["D" + who],
            "department_code": "DEMO_DEPT_" + who,
            "academic_year": 1,
            "community_access": True,
        }

    def public(self, row, who):
        result = {key: value for key, value in row.items() if key not in {"who", "deleted"}}
        result["is_mine"] = row["who"] == who
        if self.fault == "anon-leak" and "display_name" in result:
            result["author_id"] = IDS["A"]
        return result

    def __call__(self, request):
        path = request.url.path.removeprefix("/api/v1")
        body = json.loads(request.content) if request.content else {}
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        who = self.tokens.get(token)
        self.calls.append((request.method, path, who))
        assert (
            request.headers.get("cookie") is None
        )  # Anonymous checks use no ambient login cookie.
        if path == "/auth/login":
            require = body.get("password") == PASSWORD and body.get("student_id") in {
                "DITDEMO_A",
                "DITDEMO_B",
            }
            if not require:
                return self.response({}, 401)
            who = body["student_id"][-1]
            self.count += 1
            self.a_logins += who == "A"
            if self.fault == "marker-change" and self.a_logins == 3:
                self.rows[IDS["POST"]]["title"] = "OTHER-RUN-DO-NOT-DELETE"
            token = "fictional-token-" + str(self.count).zfill(4)
            self.tokens[token] = who
            result = self.response(
                {
                    "token": token,
                    "token_type": "Bearer",
                    "student_id": body["student_id"],
                    "name": "Fictional " + who,
                    "record_source": "DEMO",
                }
            )
            result.headers["set-cookie"] = "ambient_cookie=not-allowed-in-followup"
            return result
        if path == "/opportunities/" + IDS["OP"]:
            return self.response(
                {
                    "id": IDS["OP"],
                    "source_kind": "DEMO",
                    "title": MARKER,
                    "platform_receives_submission": False,
                }
            )
        if not who:
            if self.fault == "password-echo":
                return httpx.Response(
                    401,
                    json={"code": "UNAUTHORIZED", "message": PASSWORD},
                    headers={"cache-control": "private, no-store"},
                )
            return self.response({}, 401)
        if path == "/auth/me":
            return self.response(self.me(who))
        if path == "/auth/logout":
            del self.tokens[token]
            return self.response({"status": "ok"})
        if path == "/me/saved-opportunities":
            items = [self.saved[who]] if who in self.saved else []
            if self.fault == "private-list-leak" and "A" in self.saved and who == "B":
                items = [self.saved["A"]]
            return self.response({"items": deepcopy(items)})
        if path.startswith("/me/saved-opportunities/"):
            return self.personal(request, path, body, who)
        return self.community(request, path, body, who)

    def community(self, request, path, body, who):
        method = request.method
        collection = "/anonymous-posts" if path.startswith("/anonymous-posts") else "/recruitments"
        if path == collection and method == "GET":
            rows = [
                self.public(row, who)
                for row in self.rows.values()
                if not row.get("deleted")
                and (("display_name" in row) == (collection == "/anonymous-posts"))
            ]
            return self.response(
                {"items": rows, "limit": 50, "offset": 0, "has_more": self.fault == "list-bound"}
            )
        if path == collection and method == "POST":
            key = (who, path, request.headers["idempotency-key"])
            prior = self.claims.get(key)
            if prior:
                old_body, rid = prior
                if old_body != body:
                    return self.response({}, 409)
                if self.rows[rid].get("deleted"):
                    return self.response({}, 404)
                return self.response(self.public(self.rows[rid], who), replay=True)
            rid = (
                IDS["POST"]
                if collection == "/anonymous-posts"
                else IDS["CLOSE"]
                if "close sample" in body["title"]
                else IDS["TEAM"]
            )
            row = {
                "id": rid,
                "who": who,
                "title": body["title"],
                "body": body["body"],
                "status": "active" if collection == "/anonymous-posts" else "open",
                "revision": 1,
                "created_at": "2026-10-30T00:00:00Z",
                "updated_at": "2026-10-30T00:00:00Z",
            }
            if collection == "/anonymous-posts":
                row.update(display_name="익명", comment_count=0)
            else:
                row.update(
                    owner={"display_name": "Fictional " + who},
                    field=body["field"],
                    roles=body["roles"],
                    capacity=body["capacity"],
                    accepted_count=0,
                    deadline_at=body["deadline_at"],
                    opportunity_id=None,
                )
            self.rows[rid] = row
            self.claims[key] = (body, rid)
            if self.fault == "ambiguous-create" and collection == "/anonymous-posts":
                raise httpx.ReadError("FICTIONAL-password-only should never print")
            return self.response(self.public(row, who), 201)
        rid = path.split("/")[2]
        row = self.rows.get(rid)
        if row is None or row.get("deleted"):
            return self.response({}, 404)
        if method == "GET":
            return self.response(self.public(row, who))
        if row["who"] != who and self.fault != "owner-bypass":
            return self.response({}, 404)
        expected = body.get("revision") if body else int(request.url.params.get("revision", "0"))
        if expected != row["revision"]:
            return self.response({}, 409)
        if path.endswith("/close"):
            row["status"] = "closed"
        elif method == "DELETE":
            row["deleted"] = True
            self.deleted_ids.append(rid)
            return self.response({"id": rid, "deleted": True})
        else:
            row.update({key: value for key, value in body.items() if key != "revision"})
        row["revision"] += 1
        return self.response(self.public(row, who))

    def personal(self, request, path, body, who):
        method = request.method
        parent = self.saved.get(who)
        if method == "PUT":
            if parent:
                return self.response(deepcopy(parent))
            parent = {
                "opportunity_id": IDS["OP"],
                "memo": body["memo"],
                "status": "interested",
                "revision": 1,
                "checks": [],
            }
            self.saved[who] = parent
            return self.response(deepcopy(parent), 201)
        if parent is None:
            return self.response({}, 404)
        if path.endswith("/checks"):
            key = (who, path, request.headers["idempotency-key"])
            if key in self.claims:
                row = next(
                    (item for item in parent["checks"] if item["id"] == self.claims[key]), None
                )
                return self.response(deepcopy(row)) if row else self.response({}, 409)
            row = {"id": IDS["CHECK"], **body, "completed_at": None, "revision": 1}
            self.claims[key] = row["id"]
            parent["checks"].append(row)
            return self.response(deepcopy(row), 201)
        is_check = "/checks/" in path
        row = (
            next((item for item in parent["checks"] if item["id"] == path.rsplit("/", 1)[1]), None)
            if is_check
            else parent
        )
        if row is None:
            return self.response({}, 404)
        if int(request.headers["if-match"].strip('"')) != row["revision"]:
            return self.response({}, 409)
        if method == "DELETE":
            if is_check:
                parent["checks"].remove(row)
            else:
                del self.saved[who]
            return self.response({"deleted": True})
        row.update(body)
        row["revision"] += 1
        if body.get("completed"):
            row["completed_at"] = "2026-10-30T00:00:00Z"
        return self.response(deepcopy(row))


def execute(wire=None, **env):
    wire = wire or Wire()
    config = check.Config.from_environment(environment() | env)
    report = check.run_check(config, transport=httpx.MockTransport(wire))
    return report, wire


def test_full_mock_contract_relogin_negative_cases_and_exact_cleanup():
    report, wire = execute()
    assert report["status"] == "PASS_HTTP_SCOPE"
    assert report["overall_project"] == "NOT_VERIFIED"
    assert report["failed_stage"] is None
    assert set(report["cleanup"]) == {"post", "recruitment", "saved", "check"}
    assert all(value == "VERIFIED_LOGICAL_DELETE" for value in report["cleanup"].values())
    assert wire.deleted_ids == [IDS["POST"], IDS["TEAM"]]
    assert not wire.tokens and not wire.saved
    assert "role_or_department_change_requires_operator" in report["not_run"]
    assert all(
        method != "DELETE"
        or path.rsplit("/", 1)[-1] in {IDS["POST"], IDS["TEAM"], IDS["CHECK"], IDS["OP"]}
        for method, path, _ in wire.calls
    )


@pytest.mark.parametrize("flags", [{}, {check.OPT_IN: "1"}, {check.APPROVED: "1"}])
def test_default_never_loads_credentials_or_constructs_client(monkeypatch, capsys, flags):
    loader = Mock(side_effect=AssertionError("credential loading forbidden"))
    client = Mock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(check.Config, "from_environment", loader)
    monkeypatch.setattr(check.httpx, "Client", client)
    assert check.main(flags) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "NOT_RUN"
    loader.assert_not_called()
    client.assert_not_called()


@pytest.mark.parametrize(
    "target",
    [
        "https://example.invalid:443",
        "http://127.0.0.1:8000/path",
        "http://user:password@localhost:8000",
        "http://localhost:8000?token=secret",
        "http://localhost",
        "file:///tmp/x",
        "http://127.0.0.1:99999",
        "http://127.0.0.1:8000/#secret",
    ],
)
def test_only_explicit_loopback_origin_is_accepted(target):
    with pytest.raises(check.CheckFailed):
        check.Config.from_environment(environment() | {"DIT_API_P0_CHECK_BASE_URL": target})


def test_invalid_config_cli_output_is_secret_safe_and_does_not_connect(monkeypatch, capsys):
    client = Mock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(check.httpx, "Client", client)
    assert (
        check.main(
            environment()
            | {
                "DIT_API_P0_CHECK_BASE_URL": "http://private:FICTIONAL-password-only@remote.invalid:8000"
            }
        )
        == 2
    )
    output = capsys.readouterr().out
    assert PASSWORD not in output and "remote.invalid" not in output
    client.assert_not_called()


@pytest.mark.parametrize(
    "fault", ["anon-leak", "owner-bypass", "private-list-leak", "password-echo"]
)
def test_actual_negative_response_counterexamples_cannot_report_pass(fault):
    report, wire = execute(Wire(fault))
    assert report["status"] == "NOT_VERIFIED" and report["failed_stage"] is not None
    output = json.dumps(report)
    assert PASSWORD not in output and IDS["A"] not in output and "fictional-token" not in output


def test_cleanup_refuses_changed_marker_instead_of_deleting_another_record():
    report, wire = execute(Wire("marker-change"))
    assert report["status"] == "NOT_VERIFIED"
    assert report["cleanup"]["post"] == "NOT_VERIFIED"
    assert IDS["POST"] not in wire.deleted_ids
    assert wire.rows[IDS["POST"]]["title"] == "OTHER-RUN-DO-NOT-DELETE"


def test_ambiguous_write_is_not_bulk_deleted_or_reported_clean():
    report, wire = execute(Wire("ambiguous-create"))
    assert report["status"] == "NOT_VERIFIED"
    assert report["unresolved_create_responses"] == 1
    assert wire.deleted_ids == [] and IDS["POST"] in wire.rows
    assert PASSWORD not in json.dumps(report)


def test_closed_sample_retention_is_explicit_not_false_cleanup_success():
    report, wire = execute(**{"DIT_API_P0_CHECK_CLOSE_SAMPLE": "1"})
    assert report["checks"]["owner_close_separate_sample"] == "PASS"
    assert report["cleanup"]["closed_sample"] == "NOT_VERIFIED_CLOSED_ROW_REMAINS"
    assert report["status"] == "NOT_VERIFIED"
    assert wire.rows[IDS["CLOSE"]]["status"] == "closed"
    assert IDS["CLOSE"] not in wire.deleted_ids


def test_bounded_public_list_never_claims_complete_deletion_proof():
    report, _ = execute(Wire("list-bound"))
    assert report["status"] == "NOT_VERIFIED"
    assert report["cleanup"]["recruitment"] == "NOT_VERIFIED"


def test_http_client_never_uses_environment_proxy_or_redirects(monkeypatch):
    original = check.httpx.Client
    captured = []

    def factory(**kwargs):
        captured.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(check.httpx, "Client", factory)
    execute()
    assert captured[0]["trust_env"] is False and captured[0]["follow_redirects"] is False
    assert captured[0]["timeout"] == 5


@pytest.mark.parametrize("fault", ["redirect", "network-error"])
def test_redirect_and_transport_exception_never_escape_or_echo_secrets(fault):
    requests = []

    def handler(request):
        requests.append(request)
        if fault == "redirect":
            return httpx.Response(307, headers={"Location": "https://outside.invalid/secret"})
        raise httpx.ReadError("synthetic-secret-" + PASSWORD)

    config = check.Config.from_environment(environment())
    report = check.run_check(config, transport=httpx.MockTransport(handler))
    assert len(requests) == 1
    assert str(requests[0].url).startswith(config.base_url)
    assert report["status"] == "NOT_VERIFIED"
    assert report["failed_stage"] == "AUTHENTICATION"
    assert PASSWORD not in json.dumps(report) and "outside.invalid" not in json.dumps(report)
