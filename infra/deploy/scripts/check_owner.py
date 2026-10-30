"""Owner-invoked, read-only host preflight plus an exclusive outside-repo metadata snapshot.

Never read API env/CA contents; never start, stop, build, deploy or modify Docker/Tunnel/DB.
Docker compose config is quiet: resolved configuration and credentials are never printed.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "ditnow-campus"
SHA = re.compile(r"[0-9a-f]{40}\Z")
KEYS = {"DITNOW_RELEASE_SHA", "DITNOW_API_ENV_FILE", "DITNOW_DB_CA_FILE"}


class Failure(Exception):
    pass


def run(args):
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
        env={key: value for key, value in os.environ.items() if key not in KEYS},
    )
    if result.returncode:
        raise Failure("COMMAND_FAILED_NO_RAW_OUTPUT")
    return result.stdout


def outside_file(value, *, private=False):
    path = Path(value)
    if (
        not path.is_absolute()
        or not path.is_file()
        or path.resolve().is_relative_to(ROOT.resolve())
    ):
        raise Failure("OUTSIDE_REPOSITORY_FILE_REQUIRED")
    if private and os.name == "posix" and path.stat().st_mode & 0o077:
        raise Failure("PRIVATE_ENV_PERMISSIONS_REQUIRED")
    return path.resolve()


def pointers(path):
    path = outside_file(path)
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if (
            not sep
            or key not in KEYS
            or key in values
            or not value
            or any(c in value for c in "$`#\"'\r\n")
        ):
            raise Failure("POINTER_FILE_INVALID")
        values[key] = value
    if set(values) != KEYS or not SHA.fullmatch(values["DITNOW_RELEASE_SHA"]):
        raise Failure("EXACT_GIT_SHA_REQUIRED")
    outside_file(values["DITNOW_API_ENV_FILE"], private=True)
    outside_file(values["DITNOW_DB_CA_FILE"])
    return values


def check_source(sha):
    if not SHA.fullmatch(sha) or run(["git", "rev-parse", "HEAD"]).strip() != sha:
        raise Failure("SOURCE_SHA_MISMATCH")
    if run(["git", "status", "--porcelain", "--untracked-files=normal"]).strip():
        raise Failure("SOURCE_NOT_CLEAN")


def check_docker_environment():
    # Explicit contexts override DOCKER_HOST. Never silently select another daemon.
    if os.environ.get("DOCKER_CONTEXT"):
        raise Failure("EXPLICIT_DOCKER_CONTEXT_REVIEW_REQUIRED")
    endpoint = os.environ.get("DOCKER_HOST")
    if endpoint and not endpoint.startswith("unix://"):
        raise Failure("LOCAL_DOCKER_SOCKET_REQUIRED")


def other_containers():
    fmt = '{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.State}}\t{{.Label "com.docker.compose.project"}}'
    records = []
    for line in run(["docker", "ps", "-a", "--format", fmt]).splitlines():
        fields = line.split("\t")
        if len(fields) != 5:
            raise Failure("CONTAINER_METADATA_INVALID")
        if fields[4] != PROJECT:
            records.append(dict(zip(("id", "name", "image", "state"), fields[:4], strict=True)))
    return sorted(records, key=lambda row: row["id"])


def listeners():
    result = {}
    for line in run(["ss", "-H", "-ltn"]).splitlines():
        fields = line.split()
        if len(fields) >= 4:
            address = fields[3]
            port = address.rsplit(":", 1)[-1]
            if port in {"18080", "18000"}:
                result.setdefault(port, []).append(address)
    return result


def preflight(deploy_env, snapshot, tunnel_confirmed):
    if sys.platform != "linux":
        raise Failure("LINUX_HOST_REQUIRED")
    if not tunnel_confirmed:
        raise Failure("TUNNEL_HOST_NETWORK_UNVERIFIED")
    check_docker_environment()
    values = pointers(deploy_env)
    check_source(values["DITNOW_RELEASE_SHA"])
    # A remote Docker daemon would not share the namespace tested by local ss.
    endpoint = (
        os.environ.get("DOCKER_HOST")
        or run(["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]).strip()
    )
    if not endpoint.startswith("unix://"):
        raise Failure("LOCAL_DOCKER_SOCKET_REQUIRED")
    if run(["docker", "info", "--format", "{{.OSType}}"]).strip() != "linux":
        raise Failure("LINUX_DOCKER_REQUIRED")
    version = run(["docker", "compose", "version", "--short"]).strip()
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", version)
    if not match or tuple(map(int, match.groups())) < (2, 30, 0):
        raise Failure("COMPOSE_2_30_REQUIRED")
    if run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.docker.compose.project={PROJECT}",
            "--format",
            "{{.ID}}",
        ]
    ).strip():
        raise Failure("PROJECT_ALREADY_EXISTS_REVIEW_REQUIRED")
    if listeners():
        raise Failure("ORIGIN_PORT_ALREADY_IN_USE")
    records = other_containers()
    if len(records) != 8:
        raise Failure("EXPECTED_EIGHT_EXISTING_CONTAINERS")
    run(
        [
            "docker",
            "compose",
            "--project-name",
            PROJECT,
            "--env-file",
            str(Path(deploy_env).resolve()),
            "-f",
            str(ROOT / "infra/deploy/compose.yaml"),
            "config",
            "-q",
        ]
    )
    target = Path(snapshot)
    if not target.is_absolute() or target.resolve().is_relative_to(ROOT.resolve()):
        raise Failure("OUTSIDE_REPOSITORY_SNAPSHOT_REQUIRED")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump({"release_sha": values["DITNOW_RELEASE_SHA"], "containers": records}, stream)


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise Failure("ARGUMENTS_INVALID")


def main(argv=None):
    parser = Parser(description="Owner-only read-only preflight; no deployment", allow_abbrev=False)
    parser.add_argument("--deploy-env", required=True)
    parser.add_argument("--snapshot")
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--tunnel-host-network-confirmed", action="store_true")
    try:
        args = parser.parse_args(argv)
        if args.source_only:
            check_docker_environment()
            check_source(pointers(args.deploy_env)["DITNOW_RELEASE_SHA"])
        else:
            if args.snapshot is None:
                raise Failure("SNAPSHOT_ARGUMENT_REQUIRED")
            preflight(args.deploy_env, args.snapshot, args.tunnel_host_network_confirmed)
    except Failure as error:
        print(json.dumps({"status": "BLOCKED", "code": str(error), "deployment": "NOT_RUN"}))
        return 2
    except (OSError, ValueError, subprocess.SubprocessError):
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "code": "HOST_CHECK_FAILED",
                    "deployment": "NOT_RUN",
                }
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": "PASS",
                "deployment": "NOT_RUN",
                "check": "SOURCE_ONLY" if args.source_only else "HOST_PREFLIGHT",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
