"""Packaging contract tests and mocked probes; no Docker/network/real environment reads."""

import importlib
import json
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

    def test_public_probe_checks_spa_assets_unconfigured_auth_without_db(self):
        index = b'<div id="root"></div><script src="/assets/app.js"></script>'
        calls = []

        def get(path):
            calls.append(path)
            if path == "/api/v1/health":
                return 200, {}, b'{"data":{"status":"ok","service":"ditnow-api"}}'
            if path.startswith("/app"):
                return 200, {"Cache-Control": "no-store"}, index
            if path == "/assets/app.js":
                return 200, {}, b"public-js"
            if path == "/api/v1/auth/me":
                return 503, {}, b'{"code":"UNAVAILABLE"}'
            return 404, {}, b'{"code":"NOT_FOUND"}'

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
        self.assertIn("/app/login", calls)
        self.assertIn("/api/v1/auth/me", calls)
        self.assertIn("/assets/does-not-exist.js", calls)


if __name__ == "__main__":
    unittest.main()
