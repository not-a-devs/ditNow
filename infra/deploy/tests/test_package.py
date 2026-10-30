"""Packaging contract tests and mocked probes; no Docker/network/real environment reads."""

import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "infra/deploy/scripts"))
import check_owner as owner  # noqa: E402 - standalone script directory, no installed package
import smoke  # noqa: E402

NOSNIFF = {"X-Content-Type-Options": "nosniff"}
SHA = "a" * 40
LOCATION_PATTERN = r"(?m)^[ \t]*location[ \t]+([^{\r\n]+?)[ \t]*\{([^{}]*)\}"
# Pre-fix nginx shape: location add_header drops the inherited server-level nosniff.
ORIGINAL_NGINX_LOCATIONS = """
        add_header X-Content-Type-Options nosniff always;
        location = /index.html {
            add_header Cache-Control no-store always;
            try_files $uri =404;
        }
        location /assets/ {
            try_files $uri =404;
            add_header Cache-Control "public, max-age=31536000, immutable";
        }
        location / {
            add_header Cache-Control no-store always;
            try_files $uri $uri/ /index.html;
        }
"""
# Pre-fix README bootstrap: independent lines keep running after a failed test.
ORIGINAL_BOOTSTRAP = """
umask 077
test ! -e "$API_ENV_FILE"
cp infra/deploy/api.env.example "$API_ENV_FILE"
test ! -e "$DEPLOY_ENV_FILE"
printf 'DITNOW_RELEASE_SHA=%s\\nDITNOW_API_ENV_FILE=%s\\nDITNOW_DB_CA_FILE=%s\\n' \
"$RELEASE_SHA" "$API_ENV_FILE" "$CA_FILE" > "$DEPLOY_ENV_FILE"
chmod 600 "$API_ENV_FILE" "$DEPLOY_ENV_FILE"
"""


def locations_missing_nosniff(text):
    """Locations whose own add_header disables inheritance but lack nosniff always."""
    required = "add_header X-Content-Type-Options nosniff always;"
    missing = []
    for name, body in re.findall(LOCATION_PATTERN, text):
        if "add_header" in body and required not in body:
            missing.append(name)
    return missing


def readme_bootstrap():
    readme = (ROOT / "infra/deploy/README.md").read_text(encoding="utf-8")
    match = re.search(r"# BEGIN-DITNOW-BOOTSTRAP\n(.*?)# END-DITNOW-BOOTSTRAP\n", readme, re.S)
    if match is None:
        raise AssertionError("README bootstrap sample markers missing")
    return match.group(1)


class PackagingTests(unittest.TestCase):
    def test_explicit_context_cannot_override_local_host_before_any_command(self):
        with (
            patch.object(owner.sys, "platform", "linux"),
            patch.dict(
                owner.os.environ,
                {
                    "DOCKER_HOST": "unix:///synthetic-local.sock",
                    "DOCKER_CONTEXT": "synthetic-remote",
                },
                clear=True,
            ),
            patch.object(owner, "run") as command,
            patch.object(owner, "pointers") as pointer,
        ):
            with self.assertRaisesRegex(owner.Failure, "EXPLICIT_DOCKER_CONTEXT_REVIEW_REQUIRED"):
                owner.preflight("unused", "unused", True)
            with patch("builtins.print"):
                self.assertEqual(owner.main(["--deploy-env", "unused", "--source-only"]), 2)
            command.assert_not_called()
            pointer.assert_not_called()

    def test_context_endpoint_is_checked_before_daemon_metadata(self):
        with (
            patch.object(owner.sys, "platform", "linux"),
            patch.dict(owner.os.environ, {}, clear=True),
            patch.object(owner, "pointers", return_value={"DITNOW_RELEASE_SHA": "a" * 40}),
            patch.object(owner, "check_source"),
            patch.object(owner, "run", return_value="ssh://synthetic-remote") as command,
        ):
            with self.assertRaisesRegex(owner.Failure, "LOCAL_DOCKER_SOCKET_REQUIRED"):
                owner.preflight("unused", "unused", True)
            command.assert_called_once_with(
                ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]
            )

    def test_child_environment_cannot_override_validated_compose_pointers(self):
        with (
            patch.dict(
                owner.os.environ,
                {key: "synthetic-stale-override" for key in owner.KEYS},
                clear=True,
            ),
            patch.object(
                owner.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="")
            ) as command,
        ):
            owner.run(["docker", "compose", "config", "-q"])
        self.assertFalse(set(command.call_args.kwargs["env"]) & owner.KEYS)
        readme = (ROOT / "infra/deploy/README.md").read_text(encoding="utf-8")
        self.assertIn(
            "env -u DITNOW_RELEASE_SHA -u DITNOW_API_ENV_FILE -u DITNOW_DB_CA_FILE", readme
        )

    def test_source_only_check_never_executes_docker_or_claims_host_checks(self):
        with (
            patch.object(owner, "pointers", return_value={"DITNOW_RELEASE_SHA": "a" * 40}),
            patch.object(owner, "check_source") as source,
            patch.object(owner, "run") as command,
            patch("builtins.print") as output,
        ):
            self.assertEqual(owner.main(["--deploy-env", "synthetic.env", "--source-only"]), 0)
        source.assert_called_once_with("a" * 40)
        command.assert_not_called()
        self.assertEqual(json.loads(output.call_args.args[0])["check"], "SOURCE_ONLY")

    def test_existing_target_project_is_blocked_before_snapshot_or_config(self):
        def command(args):
            if args[1:] == ["info", "--format", "{{.OSType}}"]:
                return "linux"
            if args[1:3] == ["compose", "version"]:
                return "2.30.0"
            if args[1:3] == ["ps", "-a"]:
                return "synthetic-existing-project-id"
            raise AssertionError("unexpected command")

        with (
            patch.object(owner.sys, "platform", "linux"),
            patch.dict(owner.os.environ, {"DOCKER_HOST": "unix:///synthetic.sock"}, clear=True),
            patch.object(owner, "pointers", return_value={"DITNOW_RELEASE_SHA": "a" * 40}),
            patch.object(owner, "check_source"),
            patch.object(owner, "run", side_effect=command),
            patch.object(owner, "listeners") as ports,
        ):
            with self.assertRaisesRegex(owner.Failure, "PROJECT_ALREADY_EXISTS_REVIEW_REQUIRED"):
                owner.preflight("synthetic.env", "unused", True)
            ports.assert_not_called()

    def test_compose_only_two_host_services_without_port_maps_or_db(self):
        text = (ROOT / "infra/deploy/compose.yaml").read_text(encoding="utf-8")
        self.assertEqual(text.count("network_mode: host"), 2)
        self.assertNotIn("ports:", text)
        self.assertNotIn("container_name:", text)
        self.assertNotIn("privileged:", text)
        self.assertNotIn("ditnow_migrator", text)
        self.assertIn("format: raw", text)
        self.assertIn("create_host_path: false", text)
        self.assertIn("read_only: true", text)
        self.assertIn("/run/certs/mariadb-ca.pem", text)

    def test_images_require_sha_and_do_not_copy_legacy_mvp_or_credentials(self):
        for path in ("apps/web/Dockerfile", "services/api/Dockerfile"):
            text = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn('test "${#RELEASE_SHA}" = 40', text)
            self.assertIn("org.opencontainers.image.revision=$RELEASE_SHA", text)
            self.assertNotIn("COPY . ", text)
            self.assertNotIn("mvp", text)
            self.assertNotIn("SECRET", text)
        api = (ROOT / "services/api/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("--frozen --no-dev --no-editable", api)
        self.assertIn('"127.0.0.1", "--port", "18000"', api)
        self.assertIn('"--workers", "1"', api)
        self.assertIn('"--no-proxy-headers"', api)
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        for entry in ("mvp", "**/.env", "**/.env.*", "**/*.pem", "**/*.clixml", ".git"):
            self.assertIn(entry, ignore)

    def test_nginx_preserves_api_paths_and_only_binds_loopback(self):
        text = (ROOT / "infra/deploy/nginx.conf").read_text(encoding="utf-8")
        self.assertEqual(text.count("listen 127.0.0.1:18080"), 2)
        self.assertNotIn("listen 0.0.0.0", text)
        self.assertIn("proxy_pass http://127.0.0.1:18000;", text)
        self.assertNotIn("proxy_pass http://127.0.0.1:18000/;", text)
        self.assertIn("location /assets/ {\n            try_files $uri =404;", text)
        self.assertIn("location = /index.html", text)
        self.assertIn("Cache-Control no-store always", text)
        self.assertIn("access_log off", text)

    def test_imports_never_execute_commands_or_network(self):
        with patch("subprocess.run", side_effect=AssertionError("command forbidden")):
            importlib.reload(owner)
            importlib.reload(smoke)

    def test_owner_tunnel_confirmation_is_required_before_any_command(self):
        with (
            patch.object(owner.sys, "platform", "linux"),
            patch.object(owner, "run") as command,
        ):
            with self.assertRaisesRegex(owner.Failure, "TUNNEL_HOST_NETWORK_UNVERIFIED"):
                owner.preflight("unused", "unused", False)
            command.assert_not_called()

    def test_owner_source_mismatch_and_dirty_source_never_print_git_output(self):
        sha = "a" * 40
        with patch.object(owner, "run", side_effect=["b" * 40]):
            with self.assertRaisesRegex(owner.Failure, "SOURCE_SHA_MISMATCH"):
                owner.check_source(sha)
        with patch.object(owner, "run", side_effect=[sha, "?? synthetic-sensitive-filename"]):
            with self.assertRaisesRegex(owner.Failure, "SOURCE_NOT_CLEAN"):
                owner.check_source(sha)

    def test_pointer_file_never_reads_api_env_or_ca_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            env, ca, pointer = (
                temp / "runtime.env",
                temp / "ca.pem",
                temp / "deploy.env",
            )
            env.write_text("synthetic-private-value", encoding="utf-8")
            env.chmod(0o600)
            ca.write_text("synthetic-public-ca", encoding="utf-8")
            pointer.write_text(
                f"DITNOW_RELEASE_SHA={'a' * 40}\n"
                f"DITNOW_API_ENV_FILE={env}\nDITNOW_DB_CA_FILE={ca}\n",
                encoding="utf-8",
            )
            original = Path.read_text

            def guarded(path, **kwargs):
                self.assertEqual(path, pointer)
                return original(path, **kwargs)

            with patch.object(Path, "read_text", guarded):
                self.assertEqual(owner.pointers(str(pointer))["DITNOW_RELEASE_SHA"], "a" * 40)

    def test_owner_preflight_snapshot_and_config_are_readonly_project_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "before.json"
            records = [
                {"id": str(i), "name": f"existing-{i}", "image": "existing"} for i in range(8)
            ]
            calls = []

            def command(args):
                calls.append(args)
                if args[1:] == ["info", "--format", "{{.OSType}}"]:
                    return "linux"
                if args[1:3] == ["compose", "version"]:
                    return "2.30.0"
                return ""

            with (
                patch.object(owner.sys, "platform", "linux"),
                patch.dict(
                    owner.os.environ,
                    {"DOCKER_HOST": "unix:///synthetic.sock"},
                    clear=True,
                ),
                patch.object(owner, "pointers", return_value={"DITNOW_RELEASE_SHA": "a" * 40}),
                patch.object(owner, "check_source"),
                patch.object(owner, "listeners", return_value={}),
                patch.object(owner, "other_containers", return_value=records),
                patch.object(owner, "run", side_effect=command),
            ):
                owner.preflight("synthetic.env", str(snapshot), True)
            self.assertEqual(json.loads(snapshot.read_text())["containers"], records)
            self.assertTrue(any(args[-2:] == ["config", "-q"] for args in calls))
            self.assertFalse(
                any(
                    set(args) & {"up", "stop", "down", "build", "prune", "inspect-env"}
                    for args in calls
                )
            )

    def test_wildcard_listeners_are_not_accepted(self):
        with (
            patch.object(
                smoke,
                "get",
                return_value=(
                    200,
                    {},
                    b'{"data":{"status":"ok","service":"ditnow-api"}}',
                ),
            ),
            patch.object(
                smoke,
                "listeners",
                return_value={"18000": ["0.0.0.0:18000"], "18080": ["127.0.0.1:18080"]},
            ),
        ):
            with self.assertRaisesRegex(owner.Failure, "LOOPBACK_BIND_REQUIRED"):
                smoke.probe(1)

    def _public_probe(self, without_nosniff=None):
        """Run the probe against a mocked loopback; drop nosniff on one path prefix."""
        index = b'<div id="root"></div><script src="/assets/app.js"></script>'
        calls = []

        def headers(path, extra=None):
            base = dict(extra or {})
            if without_nosniff is None or not path.startswith(without_nosniff):
                base.update(NOSNIFF)
            return base

        def get(path):
            calls.append(path)
            if path == "/api/v1/health":
                return 200, headers(path), b'{"data":{"status":"ok","service":"ditnow-api"}}'
            if path.startswith("/app"):
                return 200, headers(path, {"Cache-Control": "no-store"}), index
            if path == "/assets/app.js":
                return 200, headers(path), b"public-js"
            if path == "/api/v1/auth/me":
                return 503, headers(path), b'{"code":"UNAVAILABLE"}'
            return 404, headers(path), b'{"code":"NOT_FOUND"}'

        with (
            patch.object(smoke, "get", side_effect=get),
            patch.object(
                smoke,
                "listeners",
                return_value={
                    "18000": ["127.0.0.1:18000"],
                    "18080": ["127.0.0.1:18080"],
                },
            ),
        ):
            smoke.probe(1)
        return calls

    def test_public_probe_checks_spa_assets_unconfigured_auth_without_db(self):
        calls = self._public_probe()
        self.assertIn("/app/login", calls)
        self.assertIn("/api/v1/auth/me", calls)
        self.assertIn("/assets/does-not-exist.js", calls)

    def test_public_probe_rejects_missing_nosniff_on_spa_asset_and_health(self):
        for prefix, code in (
            ("/app/login", "SPA_NOSNIFF_MISSING"),
            ("/app", "SPA_NOSNIFF_MISSING"),
            ("/assets/app.js", "ASSET_NOSNIFF_MISSING"),
            ("/api/v1/health", "API_HEALTH_NOSNIFF_MISSING"),
        ):
            with self.subTest(prefix=prefix):
                with self.assertRaisesRegex(owner.Failure, code):
                    self._public_probe(without_nosniff=prefix)

    def test_nosniff_header_value_must_be_exact(self):
        self.assertTrue(smoke.nosniff({"X-Content-Type-Options": "nosniff"}))
        self.assertFalse(smoke.nosniff({}))
        self.assertFalse(smoke.nosniff({"X-Content-Type-Options": "sniff"}))
        self.assertFalse(smoke.nosniff({"X-Content-Type-Options": "nosniff, nosniff"}))

    def test_nginx_locations_overriding_headers_repeat_nosniff(self):
        text = (ROOT / "infra/deploy/nginx.conf").read_text(encoding="utf-8")
        self.assertIn("        add_header X-Content-Type-Options nosniff always;\n", text)
        self.assertEqual(locations_missing_nosniff(text), [])
        overriding = [
            name
            for name, body in re.findall(LOCATION_PATTERN, text)
            if "add_header" in body
        ]
        # Not vacuous: index, assets and SPA fallback all override inherited headers.
        self.assertEqual(sorted(overriding), ["/", "/assets/", "= /index.html"])

    def test_original_nginx_location_headers_are_detected_as_missing_nosniff(self):
        self.assertEqual(
            sorted(locations_missing_nosniff(ORIGINAL_NGINX_LOCATIONS)),
            ["/", "/assets/", "= /index.html"],
        )


@unittest.skipUnless(
    sys.platform.startswith("linux") and shutil.which("bash"),
    "bash bootstrap sample is exercised on Linux only",
)
class OwnerBootstrapTests(unittest.TestCase):
    """Runs the README sample in isolated temp dirs with synthetic template/values only."""

    TEMPLATE = "SYNTHETIC_TEMPLATE_ONLY=1\n"
    PRIVATE = "SYNTHETIC_OWNER_PRIVATE_VALUE=do-not-overwrite\n"

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temp = Path(directory.name)
        self.repo = self.temp / "checkout"
        (self.repo / "infra/deploy").mkdir(parents=True)
        (self.repo / "infra/deploy/api.env.example").write_text(self.TEMPLATE, encoding="utf-8")
        self.private = self.temp / "private"
        self.private.mkdir()
        self.api = self.private / "ditnow-api.env"
        self.deploy = self.private / "ditnow-deploy.env"
        self.ca = self.private / "mariadb-ca.pem"

    def run_shell(self, script, **overrides):
        values = {
            "RELEASE_SHA": SHA,
            "API_ENV_FILE": str(self.api),
            "DEPLOY_ENV_FILE": str(self.deploy),
            "CA_FILE": str(self.ca),
        }
        values.update(overrides)
        path = self.temp / "owner.sh"
        path.write_text(script, encoding="utf-8")
        return subprocess.run(
            ["bash", "--noprofile", "--norc", str(path)],
            cwd=self.repo,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C", **values},
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def bootstrap(self, call="ditnow_bootstrap\n", **overrides):
        return self.run_shell(readme_bootstrap() + call, **overrides)

    def write_private(self, path):
        path.write_text(self.PRIVATE, encoding="utf-8")
        path.chmod(0o600)

    def assert_private_preserved(self, path, result):
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.read_text(encoding="utf-8"), self.PRIVATE)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("do-not-overwrite", result.stdout + result.stderr)
        self.assertNotIn(str(self.private), result.stdout + result.stderr)

    def test_readme_no_longer_documents_independent_check_then_copy(self):
        readme = (ROOT / "infra/deploy/README.md").read_text(encoding="utf-8")
        self.assertNotIn("cp infra/deploy/api.env.example", readme)
        self.assertNotIn('test ! -e "$API_ENV_FILE"\n', readme)
        sample = readme_bootstrap()
        self.assertIn("set -eu", sample)
        self.assertIn("set -o noclobber", sample)
        self.assertIn("ditnow_bootstrap() (", sample)

    def test_original_sequence_overwrites_existing_runtime_env(self):
        # Counterexample proving the pre-fix instructions were unsafe.
        self.write_private(self.api)
        self.run_shell(ORIGINAL_BOOTSTRAP)
        self.assertEqual(self.api.read_text(encoding="utf-8"), self.TEMPLATE)

    def test_creates_private_runtime_and_pointer_files_without_output(self):
        result = self.bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "DITNOW_BOOTSTRAP_CREATED\n")
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.api.read_text(encoding="utf-8"), self.TEMPLATE)
        self.assertEqual(
            self.deploy.read_text(encoding="utf-8"),
            f"DITNOW_RELEASE_SHA={SHA}\nDITNOW_API_ENV_FILE={self.api}\n"
            f"DITNOW_DB_CA_FILE={self.ca}\n",
        )
        for path in (self.api, self.deploy):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.ca.exists())

    def test_existing_runtime_env_is_never_overwritten(self):
        self.write_private(self.api)
        result = self.bootstrap()
        self.assert_private_preserved(self.api, result)
        self.assertIn("TARGET_EXISTS", result.stderr)
        self.assertFalse(self.deploy.exists())

    def test_existing_pointer_blocks_before_runtime_env_is_created(self):
        self.write_private(self.deploy)
        result = self.bootstrap()
        self.assert_private_preserved(self.deploy, result)
        self.assertFalse(self.api.exists())

    def test_existing_ca_is_never_used_as_a_write_target(self):
        self.write_private(self.ca)
        for target in ("API_ENV_FILE", "DEPLOY_ENV_FILE"):
            with self.subTest(target=target):
                result = self.bootstrap(**{target: str(self.ca)})
                self.assert_private_preserved(self.ca, result)
                self.assertIn("PATHS_NOT_DISTINCT", result.stderr)
        self.assertFalse(self.api.exists())
        self.assertFalse(self.deploy.exists())

    def test_errexit_disabled_caller_context_still_stops(self):
        # `f || ...` disables set -e inside f; explicit fail steps must still stop writes.
        self.write_private(self.api)
        result = self.bootstrap(call="ditnow_bootstrap || exit 7\n")
        self.assertEqual(result.returncode, 7)
        self.assert_private_preserved(self.api, result)
        self.assertFalse(self.deploy.exists())

    def test_dangling_symlink_target_is_not_followed(self):
        outside = self.temp / "outside-target"
        self.api.symlink_to(outside)
        result = self.bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(outside.exists())
        self.assertFalse(self.deploy.exists())

    def test_invalid_sha_relative_or_unsafe_paths_write_nothing(self):
        for overrides, code in (
            ({"RELEASE_SHA": "REPLACE_WITH_APPROVED_40_CHARACTER_SHA"}, "RELEASE_SHA_INVALID"),
            ({"RELEASE_SHA": "a" * 39}, "RELEASE_SHA_INVALID"),
            ({"API_ENV_FILE": "relative.env"}, "PATH_NOT_ABSOLUTE"),
            ({"CA_FILE": ""}, "PATH_NOT_ABSOLUTE"),
            ({"DEPLOY_ENV_FILE": str(self.deploy) + "\nINJECT=1"}, "PATH_CHARACTERS_UNSAFE"),
        ):
            with self.subTest(code=code, overrides=overrides):
                result = self.bootstrap(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(code, result.stderr)
                self.assertEqual(list(self.private.iterdir()), [])
                self.assertEqual(list(self.repo.glob("*.env")), [])


if __name__ == "__main__":
    unittest.main()
