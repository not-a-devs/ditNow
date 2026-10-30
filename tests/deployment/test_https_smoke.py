"""Offline-only owner smoke regression tests; no public domain or credentials."""

import contextlib
import io
import json
import ssl
import unittest
from unittest.mock import MagicMock, patch

import https_smoke as smoke

HTML = b'<html><div id="root"></div><script type="module" src="/assets/app.js"></script><link rel="stylesheet" href="/assets/app.css"></html>'
ENABLED = {smoke.RUN: "1", smoke.APPROVED: "1"}


def response(status=200, body=b"", content_type="application/json", **headers):
    return smoke.Response(status, {"content-type": content_type, **headers}, body)


def fixture():
    data = {
        "/app": response(body=HTML, content_type="text/html"),
        "/app/ai": response(body=HTML, content_type="text/html"),
        "/api/v1/health": response(
            body=b'{"data":{"status":"ok","service":"ditnow-api"},"server_time":"ignored"}'
        ),
        "/assets/app.js": response(
            body=b'const safety=["localhost","127.0.0.1","[::1]"]; const ns="http://www.w3.org/2000/svg";',
            content_type="text/javascript",
        ),
        "/assets/app.css": response(body=b"body{color:black}", content_type="text/css"),
    }
    for route in smoke.PRIVATE:
        data[route] = response(
            401, b'{"code":"UNAUTHORIZED"}', **{"cache-control": "private, no-store"}
        )
    return data


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.socket_guard = patch(
            "socket.create_connection", side_effect=AssertionError("NETWORK_FORBIDDEN")
        )
        self.socket_guard.start()
        self.addCleanup(self.socket_guard.stop)
        self.calls = []
        self.responses = fixture()

    def fetch(self, url):
        self.calls.append(url)
        return self.responses[url.removeprefix(smoke.TARGET)]

    def run_fixture(self):
        return smoke.run_smoke(ENABLED, self.fetch)

    def codes(self, report):
        return {item.get("code") for item in report["checks"]}

    def test_default_and_each_incomplete_gate_never_call_transport(self):
        for env in (
            {},
            {smoke.RUN: "1"},
            {smoke.APPROVED: "1"},
            {smoke.RUN: "true", smoke.APPROVED: "1"},
            {smoke.RUN: "1", smoke.APPROVED: "true"},
        ):
            with self.subTest(env=env):
                report = smoke.run_smoke(env, self.fetch)
                self.assertEqual(report["status"], "NOT_RUN")
                self.assertEqual(report["requests"], 0)
                self.assertFalse(report["verified_claim"])
        self.assertEqual(self.calls, [])

    def test_default_only_reads_run_flag(self):
        class Gate(dict):
            def get(self, key, default=None):
                if key != smoke.RUN:
                    raise AssertionError("Unexpected environment inspection")

        self.assertEqual(smoke.run_smoke(Gate(), self.fetch)["status"], "NOT_RUN")

    def test_success_is_only_public_smoke_not_authenticated_or_deployment_approval(
        self,
    ):
        report = self.run_fixture()
        self.assertEqual(report["status"], "PUBLIC_SMOKE_PASS")
        self.assertEqual(report["authenticated_crud"], "NOT_RUN")
        self.assertEqual(report["deployment_approval"], "NOT_VERIFIED")
        self.assertFalse(report["verified_claim"])
        self.assertEqual(report["requests"], 7)
        self.assertEqual(report["assets_checked"], 2)
        self.assertEqual(len(set(self.calls)), len(self.calls))
        self.assertTrue(all(item["status"] == "PASS" for item in report["checks"]))

    def test_url_rejected_before_transport_creation(self):
        invalid = [
            "http://dit.sunghae.xyz/app",
            "https://evil.example/app",
            "https://user:secret@dit.sunghae.xyz/app",
            "https://dit.sunghae.xyz:443/app",
            "https://dit.sunghae.xyz.evil.example/app",
            "https://DIT.sunghae.xyz/app",
            "https://dit.sunghae.xyz/app?",
            "https://dit.sunghae.xyz/app#",
            "https://dit.sunghae.xyz/app?q=secret",
            "https://dit.sunghae.xyz/app#secret",
            "https://dit.sunghae.xyz/a/../app",
            "https://dit.sunghae.xyz/a/%2e%2e/app",
            "https://dit.sunghae.xyz/a%2fapp",
            "https://dit.sunghae.xyz/a%5capp",
            "https://dit.sunghae.xyz/\\evil",
            "https://dit.sunghae.xyz/\napp",
        ]
        with patch.object(smoke.http.client, "HTTPSConnection") as connection:
            for url in invalid:
                with (
                    self.subTest(url=url),
                    self.assertRaisesRegex(smoke.SmokeError, "URL_REJECTED"),
                ):
                    smoke.fetch_https(url)
            connection.assert_not_called()

    def test_fixed_origin_cannot_be_overridden_with_environment(self):
        smoke.run_smoke(
            {
                **ENABLED,
                "TARGET": "https://evil.example",
                "HTTPS_PROXY": "https://evil.example",
            },
            self.fetch,
        )
        self.assertTrue(all(url.startswith(smoke.TARGET + "/") for url in self.calls))

    def test_transport_uses_verified_tls_bounded_timeout_only_get_no_auth(self):
        wire = MagicMock()
        wire.status = 307
        wire.read.return_value = b""
        wire.getheaders.return_value = [("Location", "https://evil.example")]
        connection = MagicMock()
        connection.getresponse.return_value = wire
        with patch.object(
            smoke.http.client, "HTTPSConnection", return_value=connection
        ) as constructor:
            result = smoke.fetch_https(smoke.TARGET + "/app")
        self.assertEqual(
            result.status, 307
        )  # No redirect is followed here or by the caller.
        args, kwargs = constructor.call_args
        self.assertEqual(args, (smoke.HOST,))
        self.assertEqual(kwargs["timeout"], 5)
        self.assertEqual(kwargs["port"], 443)
        self.assertEqual(kwargs["context"].verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(kwargs["context"].check_hostname)
        connection.request.assert_called_once()
        self.assertEqual(connection.request.call_args.args, ("GET", "/app"))
        self.assertFalse(
            {"authorization", "cookie"}
            & {key.lower() for key in connection.request.call_args.kwargs["headers"]}
        )
        wire.read.assert_called_once_with(smoke.MAX_BODY_BYTES + 1)
        connection.close.assert_called_once()

    def test_redirects_never_follow_location_and_are_failures(self):
        for status in (301, 302, 307, 308):
            with self.subTest(status=status):
                self.calls.clear()
                self.responses["/app"] = response(
                    status, location="https://evil.example/steal"
                )
                result = self.run_fixture()
                self.assertEqual(result["status"], "FAIL")
                self.assertIn("REDIRECT_REJECTED", self.codes(result))
                self.assertFalse(any("evil" in url for url in self.calls))

    def test_tls_and_transport_failures_never_echo_details_or_retry(self):
        for error, code in (
            (ssl.SSLCertVerificationError("secret-certificate-value"), "TLS_ERROR"),
            (OSError("secret-password-value"), "NETWORK_ERROR"),
            (smoke.SmokeError("secret-provider-value"), "RESPONSE_INVALID"),
        ):
            calls = []

            def failing(url, calls=calls, error=error):
                calls.append(url)
                raise error

            with self.subTest(code=code):
                report = smoke.run_smoke(ENABLED, failing)
                self.assertEqual(report["status"], "FAIL")
                self.assertIn(code, self.codes(report))
                self.assertNotIn("secret", json.dumps(report))
                self.assertEqual(len(calls), len(set(calls)))

    def test_private_404_503_never_count_as_ready(self):
        for route in smoke.PRIVATE:
            for status in (404, 503):
                with self.subTest(route=route, status=status):
                    self.responses = fixture()
                    self.responses[route] = response(status, b'{"code":"UNAVAILABLE"}')
                    self.assertIn("AUTH_NOT_READY", self.codes(self.run_fixture()))

    def test_private_success_or_missing_no_store_or_wrong_body_fail(self):
        invalid = [
            response(200),
            response(401, b'{"code":"UNAUTHORIZED"}'),
            response(
                401,
                b'{"code":"UNAUTHORIZED"}',
                content_type="text/html",
                **{"cache-control": "no-store"},
            ),
            response(401, b'{"code":"FORBIDDEN"}', **{"cache-control": "no-store"}),
        ]
        for value in invalid:
            with self.subTest(value=value):
                self.responses["/api/v1/auth/me"] = value
                self.assertEqual(self.run_fixture()["status"], "FAIL")

    def test_health_requires_expected_json_not_html_fallback_or_wrong_service(self):
        for value in (
            response(body=b"{}"),
            response(body=b'{"data":{"status":"ok","service":"other"}}'),
            response(body=HTML, content_type="text/html"),
        ):
            self.responses["/api/v1/health"] = value
            self.assertIn("HEALTH_INVALID", self.codes(self.run_fixture()))

    def test_spa_routes_require_root_module_and_same_release(self):
        for body, code in (
            (b"<html>not SPA</html>", "SPA_INVALID"),
            (HTML.replace(b"app.js", b"other.js"), "SPA_RELEASE_MISMATCH"),
        ):
            self.responses["/app/ai"] = response(body=body, content_type="text/html")
            self.assertIn(code, self.codes(self.run_fixture()))

    def test_spa_base_refresh_or_embedded_entry_cannot_skip_asset_validation(self):
        for body in (
            HTML + b'<base href="https://evil.example/">',
            HTML + b'<meta http-equiv="refresh" content="0;url=https://evil.example">',
            HTML.replace(b"/assets/app.js", b"data:text/javascript,export{}"),
        ):
            self.responses["/app"] = response(body=body, content_type="text/html")
            self.assertIn("SPA_INVALID", self.codes(self.run_fixture()))

    def test_external_asset_and_srcset_never_requested(self):
        for element in (
            '<script type="module" src="https://evil.example/a.js"></script>',
            '<img srcset="https://evil.example/a.png 1x">',
            '<div style="background:url(https://evil.example/a.png)"></div>',
        ):
            with self.subTest(element=element):
                self.calls.clear()
                self.responses["/app"] = response(
                    body=HTML + element.encode(), content_type="text/html"
                )
                self.assertEqual(self.run_fixture()["status"], "FAIL")
                self.assertFalse(any("evil" in url for url in self.calls))

    def test_actual_mixed_private_or_external_api_literals_fail_but_bare_safety_hosts_do_not(
        self,
    ):
        literals = [
            "http://127.0.0.1:8753/api/v1",
            "https://10.1.2.3/api/v1",
            "https://localhost/api/v1",
            "https://[::1]/api/v1",
            "http://dit.sunghae.xyz/api/v1",
            "https://other.example/api/v1",
            r"http:\/\/localhost:8753/api/v1",
        ]
        for value in literals:
            with self.subTest(value=value):
                self.responses["/assets/app.js"] = response(
                    body=('const base="' + value + '";').encode(),
                    content_type="text/javascript",
                )
                self.assertIn("UNSAFE_ENDPOINT_LITERAL", self.codes(self.run_fixture()))
        self.responses = fixture()
        self.assertEqual(self.run_fixture()["status"], "PUBLIC_SMOKE_PASS")

    def test_asset_fallback_html_and_missing_file_fail(self):
        for value, code in (
            (response(body=HTML, content_type="text/html"), "ASSET_TYPE_INVALID"),
            (response(404), "ASSET_UNAVAILABLE"),
        ):
            self.responses["/assets/app.js"] = value
            self.assertIn(code, self.codes(self.run_fixture()))

    def test_relative_import_css_assets_dedup_and_same_origin(self):
        self.responses["/assets/app.js"] = response(
            body=b'import("./chunk.js");import"./chunk.js";',
            content_type="text/javascript",
        )
        self.responses["/assets/chunk.js"] = response(
            body=b"export{}", content_type="text/javascript"
        )
        self.responses["/assets/app.css"] = response(
            body=b'@import "./extra.css";a{background:url(./logo.svg)}',
            content_type="text/css",
        )
        self.responses["/assets/extra.css"] = response(
            body=b"b{color:blue}", content_type="text/css"
        )
        self.responses["/assets/logo.svg"] = response(
            body=b'<svg xmlns="http://www.w3.org/2000/svg"/>',
            content_type="image/svg+xml",
        )
        result = self.run_fixture()
        self.assertEqual(result["status"], "PUBLIC_SMOKE_PASS")
        self.assertEqual(result["assets_checked"], 5)
        self.assertEqual(self.calls.count(smoke.TARGET + "/assets/chunk.js"), 1)

    def test_limits_bound_body_and_number_of_requests(self):
        with patch.object(smoke, "MAX_BODY_BYTES", 4):
            self.assertIn("BODY_LIMIT", self.codes(self.run_fixture()))
        with patch.object(smoke, "MAX_ASSETS", 1):
            result = self.run_fixture()
            self.assertIn("ASSET_LIMIT", self.codes(result))
            self.assertLessEqual(result["requests"], len(smoke.ROUTES) + 1)
        with patch.object(smoke, "MAX_TOTAL_BYTES", len(HTML)):
            self.assertIn("BODY_LIMIT", self.codes(self.run_fixture()))

    def test_malformed_transport_and_json_are_secret_safe(self):
        for value in (
            None,
            response(body=b"secret-not-json"),
            smoke.Response("secret-status", {}, b""),
            smoke.Response(401, {"secret-header": object()}, b""),
        ):
            self.responses["/api/v1/auth/me"] = value
            result = self.run_fixture()
            self.assertEqual(result["status"], "FAIL")
            self.assertNotIn("secret", json.dumps(result))

    def test_cli_default_not_run_and_arbitrary_arguments_never_echo(self):
        for argv, expected in (
            (["https_smoke.py"], 0),
            (["https_smoke.py", "secret-token"], 2),
        ):
            out = io.StringIO()
            with (
                patch.object(smoke.sys, "argv", argv),
                patch.object(smoke.os, "environ", {}),
                contextlib.redirect_stdout(out),
            ):
                self.assertEqual(smoke.main(), expected)
            report = json.loads(out.getvalue())
            self.assertEqual(report["status"], "NOT_RUN")
            self.assertNotIn("secret", out.getvalue())


if __name__ == "__main__":
    unittest.main()
