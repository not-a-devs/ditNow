"""Opt-in localhost HTTP checks. No DB/seed/server setup and no credential/response output."""

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from pydantic import SecretStr

OPT_IN = "DIT_API_RUN_P0_SECURITY_CHECK"
APPROVED = "DIT_API_P0_SECURITY_CHECK_APPROVED"
ANON_KEYS = {
    "id",
    "display_name",
    "title",
    "body",
    "status",
    "comment_count",
    "is_mine",
    "revision",
    "created_at",
    "updated_at",
}
ME_KEYS = {
    "user_id",
    "display_name",
    "record_source",
    "department_id",
    "department_code",
    "academic_year",
    "community_access",
}


class CheckFailed(RuntimeError):
    """Fixed internal codes only; never include response/URL/exception/secret details."""


def require(value, code="CONTRACT_MISMATCH"):
    if not value:
        raise CheckFailed(code)


def identifier(value):
    require(isinstance(value, str), "INVALID_RESOURCE_ID")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise CheckFailed("INVALID_RESOURCE_ID") from None
    require(str(parsed) == value and parsed.int != 0, "INVALID_RESOURCE_ID")
    return value


def revision(row):
    value = row.get("revision")
    require(type(value) is int and value >= 1)
    return value


def localhost_target(base):
    parsed = urlsplit(base)
    require(
        parsed.scheme in {"http", "https"}
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        and parsed.port is not None
        and 1 <= parsed.port <= 65535
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
        and not any(char.isspace() or ord(char) < 32 for char in base),
        "LOCALHOST_TARGET_REQUIRED",
    )


@dataclass(frozen=True)
class Account:
    student_id: SecretStr = field(repr=False)
    password: SecretStr = field(repr=False)


@dataclass(frozen=True)
class Config:
    base_url: str = field(repr=False)
    account_a: Account = field(repr=False)
    account_b: Account = field(repr=False)
    opportunity_id: str
    opportunity_marker: str
    close_sample: bool = False

    def __post_init__(self):
        try:
            localhost_target(self.base_url)
        except Exception:
            raise CheckFailed("LOCALHOST_TARGET_REQUIRED") from None

    @classmethod
    def from_environment(cls, env: Mapping[str, str]):
        base = env.get("DIT_API_P0_CHECK_BASE_URL", "")
        try:
            localhost_target(base)
            accounts = []
            for label in ("A", "B"):
                student = env.get(f"DIT_API_P0_CHECK_{label}_STUDENT_ID", "")
                password = env.get(f"DIT_API_P0_CHECK_{label}_PASSWORD", "")
                require(
                    re.fullmatch(rf"DITDEMO_{label}[A-Za-z0-9_-]{{0,11}}", student)
                    and 1 <= len(password) <= 64,
                    "APPROVED_DEMO_CREDENTIALS_REQUIRED",
                )
                accounts.append(Account(SecretStr(student), SecretStr(password)))
            opportunity = identifier(env.get("DIT_API_P0_CHECK_OPPORTUNITY_ID", ""))
            marker = env.get("DIT_API_P0_CHECK_OPPORTUNITY_MARKER", "")
            require(
                re.fullmatch(r"DITNOW_DEMO_[A-Za-z0-9_-]{8,60}", marker), "SEED_MARKER_REQUIRED"
            )
            return cls(
                base.rstrip("/"),
                *accounts,
                opportunity,
                marker,
                env.get("DIT_API_P0_CHECK_CLOSE_SAMPLE") == "1",
            )
        except CheckFailed:
            raise
        except Exception:
            raise CheckFailed("CONFIGURATION_INVALID") from None


class Checker:
    def __init__(self, config: Config, client: httpx.Client):
        self.config, self.client = config, client
        self.marker = "DITNOW_P0_HTTP_" + uuid4().hex
        self.tokens: list[SecretStr] = []
        self.a: SecretStr | None = None
        self.b: SecretStr | None = None
        self.me_a: dict = {}
        self.me_b: dict = {}
        self.created: dict[str, str] = {}
        self.uncertain: set[str] = set()
        self.checks: dict[str, str] = {}
        self.cleanup: dict[str, str] = {}
        self.post_body: dict = {}
        self.recruit_body: dict = {}
        self.stage = "INITIALIZATION"

    def no_credentials(self, data):
        serialized = json.dumps(data, ensure_ascii=False)
        credentials = [t.get_secret_value() for t in self.tokens]
        credentials += [
            a.student_id.get_secret_value() for a in (self.config.account_a, self.config.account_b)
        ]
        credentials += [
            a.password.get_secret_value() for a in (self.config.account_a, self.config.account_b)
        ]
        require(all(item not in serialized for item in credentials), "CREDENTIAL_RESPONSE_LEAK")

    def call(
        self, method, path, *, token=None, body=None, headers=None, statuses=(200,), private=True
    ):
        merged = dict(headers or {})
        if token is not None:
            merged["Authorization"] = "Bearer " + token.get_secret_value()
        # Anonymous checks must not accidentally reuse cookies issued by the login endpoint.
        self.client.cookies.clear()
        try:
            with self.client.stream(
                method, "/api/v1" + path, json=body, headers=merged
            ) as response:
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    require(len(raw) <= 256_000, "RESPONSE_TOO_LARGE")
                require(response.status_code in statuses, "HTTP_STATUS_UNEXPECTED")
                if private:
                    directives = {
                        s.strip().lower()
                        for s in response.headers.get("cache-control", "").split(",")
                    }
                    require({"private", "no-store"} <= directives, "PRIVATE_CACHE_POLICY_MISSING")
                value = json.loads(raw)
                require(isinstance(value, dict))
                if response.status_code >= 400:
                    require(
                        set(value) <= {"code", "message", "field_errors", "retryable", "request_id"}
                    )
                    require(
                        value.get("code")
                        == {
                            400: "VALIDATION",
                            401: "UNAUTHORIZED",
                            403: "FORBIDDEN",
                            404: "NOT_FOUND",
                            409: "CONFLICT",
                        }.get(response.status_code)
                    )
                    self.no_credentials(value)
                    return value, dict(response.headers)
                require(set(value) <= {"data", "resource_version", "server_time"})
                require(isinstance(value.get("data"), dict))
                return value["data"], dict(response.headers)
        except CheckFailed:
            raise
        except Exception:
            raise CheckFailed("HTTP_OR_RESPONSE_FAILURE") from None

    def login(self, account):
        data, _ = self.call(
            "POST",
            "/auth/login",
            body={
                "student_id": account.student_id.get_secret_value(),
                "password": account.password.get_secret_value(),
            },
        )
        require(set(data) == {"token", "token_type", "student_id", "name", "record_source"})
        require(data["token_type"] == "Bearer" and data["record_source"] == "DEMO")
        require(data["student_id"] == account.student_id.get_secret_value())
        raw = data["token"]
        require(isinstance(raw, str) and re.fullmatch(r"[A-Za-z0-9._~+/-]{8,512}={0,2}", raw))
        require(raw not in [token.get_secret_value() for token in self.tokens], "TOKEN_REUSED")
        token = SecretStr(raw)
        self.tokens.append(token)
        return token

    def me(self, token):
        data, _ = self.call("GET", "/auth/me", token=token)
        require(set(data) == ME_KEYS)
        identifier(data["user_id"])
        identifier(data["department_id"])
        require(data["record_source"] == "DEMO" and data["community_access"] is True)
        require(isinstance(data["display_name"], str) and data["display_name"])
        require(isinstance(data["department_code"], str) and data["department_code"])
        require(type(data["academic_year"]) is int and data["academic_year"] > 0)
        return data

    def anonymous(self, data, *, mine):
        require(set(data) == ANON_KEYS and data["display_name"] == "익명")
        require(data["is_mine"] is mine and data["status"] == "active")
        identifier(data["id"])
        revision(data)
        serialized = json.dumps(data, ensure_ascii=False)
        private = [token.get_secret_value() for token in self.tokens]
        private += [
            self.me_a.get("user_id"),
            self.me_b.get("user_id"),
            self.me_a.get("department_id"),
            self.me_b.get("department_id"),
        ]
        private += [self.me_a.get("department_code"), self.me_b.get("department_code")]
        private += [
            self.config.account_a.student_id.get_secret_value(),
            self.config.account_b.student_id.get_secret_value(),
        ]
        require(
            all(not item or item not in serialized for item in private), "ANONYMOUS_IDENTITY_LEAK"
        )

    def track(self, kind, data):
        require(
            data.get("is_mine") is True and self.marker in data.get("title", ""),
            "OWN_RESOURCE_MARKER_MISSING",
        )
        self.created[kind] = identifier(data.get("id"))
        self.uncertain.discard(kind)

    def denied(self, method, path, *, body=None, headers=None):
        self.call(method, path, token=self.b, body=body, headers=headers, statuses=(403, 404))

    def saved(self):
        page, _ = self.call("GET", "/me/saved-opportunities", token=self.a)
        require(set(page) == {"items"} and isinstance(page["items"], list))
        found = [
            item
            for item in page["items"]
            if item.get("opportunity_id") == self.config.opportunity_id
        ]
        require(len(found) <= 1)
        return found[0] if found else None

    def run(self):
        self.stage = "AUTHENTICATION"
        self.a, self.b = self.login(self.config.account_a), self.login(self.config.account_b)
        self.me_a, self.me_b = self.me(self.a), self.me(self.b)
        require(
            self.me_a["user_id"] != self.me_b["user_id"]
            and self.me_a["department_id"] != self.me_b["department_id"],
            "DISTINCT_DEMO_ACCOUNTS_REQUIRED",
        )
        for path in ("/auth/me", "/anonymous-posts", "/recruitments", "/me/saved-opportunities"):
            self.call("GET", path, statuses=(401,))
        self.checks["login_current_identity_and_no_auth_denial"] = "PASS"

        self.stage = "SEED_PRECONDITIONS"
        opportunity, _ = self.call(
            "GET", "/opportunities/" + self.config.opportunity_id, private=False
        )
        require(
            opportunity.get("id") == self.config.opportunity_id
            and opportunity.get("source_kind") == "DEMO"
        )
        require(
            self.config.opportunity_marker in opportunity.get("title", ""), "SEED_MARKER_MISMATCH"
        )
        require(opportunity.get("platform_receives_submission") is False)
        require(self.saved() is None, "EXISTING_PERSONAL_RECORD_BLOCKED")
        other_saved, _ = self.call("GET", "/me/saved-opportunities", token=self.b)
        require(
            all(
                item.get("opportunity_id") != self.config.opportunity_id
                for item in other_saved.get("items", [])
            ),
            "EXISTING_PERSONAL_RECORD_BLOCKED",
        )
        self.checks["approved_demo_opportunity_public_projection"] = "PASS"

        self.stage = "ANONYMOUS_CRUD"
        self.post_body = {"title": self.marker + " post", "body": self.marker + " synthetic body"}
        key = {"Idempotency-Key": self.marker + "_post"}
        self.uncertain.add("post")
        post, _ = self.call(
            "POST",
            "/anonymous-posts",
            token=self.a,
            body=self.post_body,
            headers=key,
            statuses=(201,),
        )
        self.track("post", post)
        self.anonymous(post, mine=True)
        pid = self.created["post"]
        duplicate, headers = self.call(
            "POST",
            "/anonymous-posts",
            token=self.a,
            body=self.post_body,
            headers=key,
            statuses=(200, 201),
        )
        require(duplicate.get("id") == pid and headers.get("idempotent-replayed") == "true")
        self.call(
            "POST",
            "/anonymous-posts",
            token=self.a,
            body={**self.post_body, "title": self.marker + " changed intent"},
            headers=key,
            statuses=(409,),
        )
        public, _ = self.call("GET", "/anonymous-posts/" + pid, token=self.b)
        self.anonymous(public, mine=False)
        self.denied(
            "PATCH",
            "/anonymous-posts/" + pid,
            body={"title": self.marker + " denied", "revision": 1},
        )
        self.denied("DELETE", "/anonymous-posts/" + pid + "?revision=1")
        self.call(
            "PATCH",
            "/anonymous-posts/" + pid,
            body={"title": self.marker + " unauthenticated", "revision": 1},
            statuses=(401,),
        )
        self.call("DELETE", "/anonymous-posts/" + pid + "?revision=1", statuses=(401,))
        updated, _ = self.call(
            "PATCH",
            "/anonymous-posts/" + pid,
            token=self.a,
            body={"title": self.marker + " updated post", "revision": 1},
        )
        self.anonymous(updated, mine=True)
        require(revision(updated) == 2)
        self.call(
            "PATCH",
            "/anonymous-posts/" + pid,
            token=self.a,
            body={"title": self.marker + " stale", "revision": 1},
            statuses=(409,),
        )
        self.checks["anonymous_create_read_update_idempotency_cas_and_cross_owner"] = "PASS"

        self.stage = "RECRUITMENT_CRUD"
        self.recruit_body = {
            "title": self.marker + " recruitment",
            "body": self.marker + " synthetic team",
            "field": "DEMO",
            "roles": ["DEMO"],
            "capacity": 2,
            "deadline_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        }
        self.uncertain.add("recruitment")
        team, _ = self.call(
            "POST",
            "/recruitments",
            token=self.a,
            body=self.recruit_body,
            headers={"Idempotency-Key": self.marker + "_team"},
            statuses=(201,),
        )
        self.track("recruitment", team)
        rid = self.created["recruitment"]
        duplicate, headers = self.call(
            "POST",
            "/recruitments",
            token=self.a,
            body=self.recruit_body,
            headers={"Idempotency-Key": self.marker + "_team"},
            statuses=(200, 201),
        )
        require(duplicate.get("id") == rid and headers.get("idempotent-replayed") == "true")
        public, _ = self.call("GET", "/recruitments/" + rid, token=self.b)
        require(
            public.get("is_mine") is False
            and public.get("owner") == {"display_name": self.me_a["display_name"]}
        )
        self.denied(
            "PATCH", "/recruitments/" + rid, body={"title": self.marker + " denied", "revision": 1}
        )
        self.denied("DELETE", "/recruitments/" + rid + "?revision=1")
        self.denied("POST", "/recruitments/" + rid + "/close", body={"revision": 1})
        self.call(
            "PATCH",
            "/recruitments/" + rid,
            body={"title": self.marker + " unauthenticated", "revision": 1},
            statuses=(401,),
        )
        self.call("DELETE", "/recruitments/" + rid + "?revision=1", statuses=(401,))
        updated, _ = self.call(
            "PATCH",
            "/recruitments/" + rid,
            token=self.a,
            body={"title": self.marker + " updated team", "revision": 1},
        )
        require(revision(updated) == 2)
        self.call(
            "PATCH",
            "/recruitments/" + rid,
            token=self.a,
            body={"title": self.marker + " stale", "revision": 1},
            statuses=(409,),
        )
        self.checks["recruitment_create_read_update_idempotency_cas_and_cross_owner"] = "PASS"

        self.stage = "PERSONAL_OPPORTUNITY_CRUD"
        path = "/me/saved-opportunities/" + self.config.opportunity_id
        self.uncertain.add("saved")
        saved, _ = self.call("PUT", path, token=self.a, body={"memo": self.marker}, statuses=(201,))
        require(
            saved.get("opportunity_id") == self.config.opportunity_id
            and saved.get("memo") == self.marker
        )
        self.created["saved"] = self.config.opportunity_id
        self.uncertain.discard("saved")
        duplicate, _ = self.call("PUT", path, token=self.a, body={"memo": self.marker + " ignored"})
        require(duplicate.get("memo") == self.marker and revision(duplicate) == revision(saved))
        check_body = {"text": self.marker + " check", "sort_order": 0}
        key = {"Idempotency-Key": self.marker + "_check"}
        self.uncertain.add("check")
        check, _ = self.call(
            "POST", path + "/checks", token=self.a, body=check_body, headers=key, statuses=(201,)
        )
        require(check.get("text") == check_body["text"])
        cid = self.created["check"] = identifier(check.get("id"))
        self.uncertain.discard("check")
        again, _ = self.call("POST", path + "/checks", token=self.a, body=check_body, headers=key)
        require(again.get("id") == cid)
        changed, _ = self.call(
            "PATCH",
            path + "/checks/" + cid,
            token=self.a,
            body={"completed": True},
            headers={"If-Match": '"1"'},
        )
        require(revision(changed) == 2 and changed.get("completed_at") is not None)
        self.call(
            "PATCH",
            path + "/checks/" + cid,
            token=self.a,
            body={"completed": False},
            headers={"If-Match": '"1"'},
            statuses=(409,),
        )
        self.denied(
            "PATCH", path + "/checks/" + cid, body={"completed": False}, headers={"If-Match": '"2"'}
        )
        self.denied("DELETE", path + "/checks/" + cid, headers={"If-Match": '"2"'})
        changed, _ = self.call(
            "PATCH",
            path,
            token=self.a,
            body={"memo": self.marker + " updated", "status": "preparing"},
            headers={"If-Match": '"1"'},
        )
        require(revision(changed) == 2)
        self.call(
            "PATCH",
            path,
            token=self.a,
            body={"memo": self.marker + " stale"},
            headers={"If-Match": '"1"'},
            statuses=(409,),
        )
        self.denied(
            "PATCH", path, body={"memo": self.marker + " denied"}, headers={"If-Match": '"2"'}
        )
        self.denied("DELETE", path, headers={"If-Match": '"2"'})
        self.call(
            "PATCH",
            path,
            body={"memo": self.marker + " unauthenticated"},
            headers={"If-Match": '"2"'},
            statuses=(401,),
        )
        self.call("DELETE", path, headers={"If-Match": '"2"'}, statuses=(401,))
        other_saved, _ = self.call("GET", "/me/saved-opportunities", token=self.b)
        require(
            all(
                item.get("opportunity_id") != self.config.opportunity_id
                for item in other_saved.get("items", [])
            ),
            "PRIVATE_SAVED_LIST_LEAK",
        )
        self.checks["personal_save_checklist_if_match_idempotency_and_cross_owner"] = "PASS"

        self.stage = "RELOGIN_PERSISTENCE"
        old = self.a
        self.call("POST", "/auth/logout", token=old)
        self.call("GET", "/auth/me", token=old, statuses=(401,))
        self.a = self.login(self.config.account_a)
        require(self.me(self.a)["user_id"] == self.me_a["user_id"])
        self.call("GET", "/auth/me", token=old, statuses=(401,))
        post, _ = self.call("GET", "/anonymous-posts/" + pid, token=self.a)
        self.anonymous(post, mine=True)
        require(revision(post) == 2)
        team, _ = self.call("GET", "/recruitments/" + rid, token=self.a)
        require(team.get("is_mine") is True and revision(team) == 2)
        saved = self.saved()
        require(
            saved is not None
            and saved.get("memo") == self.marker + " updated"
            and revision(saved) == 2
        )
        require(
            any(item.get("id") == cid and revision(item) == 2 for item in saved.get("checks", []))
        )
        self.checks["logout_old_token_denied_and_relogin_rows_preserved"] = "PASS"
        if self.config.close_sample:
            self.uncertain.add("closed_sample")
            sample, _ = self.call(
                "POST",
                "/recruitments",
                token=self.a,
                body={**self.recruit_body, "title": self.marker + " close sample"},
                headers={"Idempotency-Key": self.marker + "_close"},
                statuses=(201,),
            )
            self.track("closed_sample", sample)
            sample, _ = self.call(
                "POST",
                "/recruitments/" + self.created["closed_sample"] + "/close",
                token=self.a,
                body={"revision": 1},
            )
            require(sample.get("status") == "closed")
            self.checks["owner_close_separate_sample"] = "PASS"

    def verify_recruitment_hidden(self, rid):
        for offset in range(0, 500, 50):
            data, _ = self.call("GET", f"/recruitments?limit=50&offset={offset}", token=self.b)
            require(isinstance(data.get("items"), list) and type(data.get("has_more")) is bool)
            require(
                all(item.get("id") != rid for item in data["items"]),
                "CANCELLED_RECRUITMENT_VISIBLE",
            )
            if not data["has_more"]:
                return
        raise CheckFailed("PUBLIC_LIST_BOUND_NOT_VERIFIED")

    def cleanup_owned(self):
        if not self.created:
            return
        # Reauthenticate this same approved account; never use B's token for A's cleanup.
        try:
            self.a = self.login(self.config.account_a)
            require(self.me(self.a)["user_id"] == self.me_a["user_id"])
        except Exception:
            self.cleanup["resources"] = "NOT_VERIFIED"
            return
        for kind in ("check", "saved", "post", "recruitment", "closed_sample"):
            if kind not in self.created:
                continue
            try:
                rid = self.created[kind]
                if kind in {"saved", "check"}:
                    path = "/me/saved-opportunities/" + self.config.opportunity_id
                    saved = self.saved()
                    require(
                        saved is not None and self.marker in saved.get("memo", ""),
                        "CLEANUP_MARKER_CHANGED",
                    )
                    if kind == "check":
                        rows = [row for row in saved.get("checks", []) if row.get("id") == rid]
                        require(
                            len(rows) == 1 and self.marker in rows[0].get("text", ""),
                            "CLEANUP_MARKER_CHANGED",
                        )
                        path += "/checks/" + rid
                        current = rows[0]
                    else:
                        current = saved
                    result, _ = self.call(
                        "DELETE",
                        path,
                        token=self.a,
                        headers={"If-Match": '"' + str(revision(current)) + '"'},
                    )
                    require(result == {"deleted": True})
                    fresh = self.saved()
                    require(
                        fresh is None
                        if kind == "saved"
                        else fresh is not None
                        and all(item.get("id") != rid for item in fresh.get("checks", []))
                    )
                    if kind == "check":
                        self.call(
                            "POST",
                            "/me/saved-opportunities/" + self.config.opportunity_id + "/checks",
                            token=self.a,
                            body={"text": self.marker + " check", "sort_order": 0},
                            headers={"Idempotency-Key": self.marker + "_check"},
                            statuses=(409,),
                        )
                else:
                    path = "/anonymous-posts/" if kind == "post" else "/recruitments/"
                    current, _ = self.call("GET", path + rid, token=self.a)
                    require(
                        current.get("is_mine") is True and self.marker in current.get("title", ""),
                        "CLEANUP_MARKER_CHANGED",
                    )
                    if kind == "closed_sample" and current.get("status") == "closed":
                        self.cleanup[kind] = "NOT_VERIFIED_CLOSED_ROW_REMAINS"
                        continue
                    deleted, _ = self.call(
                        "DELETE", path + rid + "?revision=" + str(revision(current)), token=self.a
                    )
                    require(deleted == {"id": rid, "deleted": True})
                    self.call("GET", path + rid, token=self.a, statuses=(404,))
                    self.call("GET", path + rid, token=self.b, statuses=(404,))
                    if kind == "recruitment":
                        self.verify_recruitment_hidden(rid)
                        self.call(
                            "POST",
                            "/recruitments",
                            token=self.a,
                            body=self.recruit_body,
                            headers={"Idempotency-Key": self.marker + "_team"},
                            statuses=(404,),
                        )
                    elif kind == "post":
                        self.call(
                            "POST",
                            "/anonymous-posts",
                            token=self.a,
                            body=self.post_body,
                            headers={"Idempotency-Key": self.marker + "_post"},
                            statuses=(404,),
                        )
                self.cleanup[kind] = "VERIFIED_LOGICAL_DELETE"
            except Exception:
                self.cleanup[kind] = "NOT_VERIFIED"

    def report(self):
        failure = None
        try:
            self.run()
        except Exception:
            failure = self.stage  # Fixed local stage, never the exception or response.
        finally:
            self.cleanup_owned()
            for token in self.tokens:
                try:
                    prior, _ = self.call("GET", "/auth/me", token=token, statuses=(200, 401))
                    if prior.get("code") == "UNAUTHORIZED":
                        continue
                    logged_out, _ = self.call("POST", "/auth/logout", token=token)
                    require(logged_out == {"status": "ok"})
                    self.call("GET", "/auth/me", token=token, statuses=(401,))
                except Exception:
                    self.cleanup["sessions"] = "NOT_VERIFIED"
        complete = (
            failure is None
            and not self.uncertain
            and all(value.startswith("VERIFIED_") for value in self.cleanup.values())
        )
        return {
            "status": "PASS_HTTP_SCOPE" if complete else "NOT_VERIFIED",
            "failed_stage": failure,
            "checks": self.checks,
            "cleanup": self.cleanup,
            "unresolved_create_responses": len(self.uncertain),
            "not_run": [
                "role_or_department_change_requires_operator",
                "server_restart_persistence",
                "physical_row_deletion",
                "deployment",
                *([] if self.config.close_sample else ["owner_close_happy_path"]),
            ],
            "overall_project": "NOT_VERIFIED",
        }


def run_check(config, *, transport=None):
    # No dotenv/proxy/redirect inheritance. Local HTTP only; HTTPS verification stays enabled.
    with httpx.Client(
        base_url=config.base_url,
        timeout=5,
        follow_redirects=False,
        trust_env=False,
        transport=transport,
    ) as client:
        return Checker(config, client).report()


def main(env=None):
    env = os.environ if env is None else env
    if env.get(OPT_IN) != "1" or env.get(APPROVED) != "1":
        print(
            json.dumps(
                {"status": "NOT_RUN", "reason": "EXPLICIT_LOCAL_HTTP_WRITE_APPROVAL_REQUIRED"}
            )
        )
        return 2
    try:
        result = run_check(Config.from_environment(env))
    except Exception:
        result = {
            "status": "NOT_VERIFIED",
            "reason": "CONFIGURATION_OR_HTTP_FAILURE",
            "cleanup": "NOT_VERIFIED",
        }
    print(json.dumps(result))
    return 0 if result["status"] == "PASS_HTTP_SCOPE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
