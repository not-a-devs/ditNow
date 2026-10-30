"""Explicit loopback-only public-profile container probe; no credentials, DB or external URLs.

Owner/CI must start the two containers first. Reports fixed stage names only, never bodies.
"""

import argparse
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from check_owner import Failure, listeners, other_containers

BASE = "http://127.0.0.1:18080"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise Failure("REDIRECT_FORBIDDEN")


def get(path):
    request = Request(BASE + path, headers={"Host": "dit.sunghae.xyz"})
    try:
        response = build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        return response.code, response.headers, response.read(2_000_000)


def check(condition, code):
    if not condition:
        raise Failure(code)


def nosniff(headers):
    return headers.get("X-Content-Type-Options", "").strip().lower() == "nosniff"


def probe(wait_seconds=30, snapshot=None):
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            code, health_headers, body = get("/api/v1/health")
            if code == 200 and json.loads(body)["data"] == {
                "status": "ok",
                "service": "ditnow-api",
            }:
                break
        except (OSError, ValueError, KeyError):
            pass
        if time.monotonic() >= deadline:
            raise Failure("PUBLIC_HEALTH_TIMEOUT")
        time.sleep(0.5)
    bound = listeners()
    check(
        bound == {"18000": ["127.0.0.1:18000"], "18080": ["127.0.0.1:18080"]},
        "LOOPBACK_BIND_REQUIRED",
    )
    check(nosniff(health_headers), "API_HEALTH_NOSNIFF_MISSING")
    code, headers, index = get("/app")
    check(
        code == 200
        and b'<div id="root"' in index
        and "no-store" in headers.get("Cache-Control", ""),
        "SPA_ROOT_INVALID",
    )
    check(nosniff(headers), "SPA_NOSNIFF_MISSING")
    for route in ("/app/login", "/app/community", "/app/opportunities", "/app/ai"):
        code, headers, body = get(route)
        check(
            code == 200 and body == index and "no-store" in headers.get("Cache-Control", ""),
            "SPA_DIRECT_ENTRY_INVALID",
        )
        check(nosniff(headers), "SPA_NOSNIFF_MISSING")
    assets = re.findall(rb'(?:src|href)="(/assets/[^"\s]+)"', index)
    check(bool(assets), "BUILD_ASSETS_MISSING")
    for asset in assets:
        code, headers, _ = get(asset.decode("ascii"))
        check(code == 200, "BUILD_ASSET_FAILED")
        check(nosniff(headers), "ASSET_NOSNIFF_MISSING")
    code, _, body = get("/assets/does-not-exist.js")
    check(code == 404 and body != index, "MISSING_ASSET_MUST_NOT_USE_SPA")
    for path, expected in (
        ("/api/v1/does-not-exist", 404),
        ("/api/v1/auth/me", 503),
        ("/api/v1/anonymous-posts", 404),
    ):
        code, _, body = get(path)
        check(
            code == expected and isinstance(json.loads(body), dict),
            "PUBLIC_API_BOUNDARY_FAILED",
        )
    if snapshot:
        baseline = json.loads(Path(snapshot).read_text(encoding="utf-8"))
        check(other_containers() == baseline["containers"], "EXISTING_CONTAINERS_CHANGED")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Loopback public-profile probe; no deployment")
    parser.add_argument("--wait-seconds", type=int, choices=range(1, 61), default=30)
    parser.add_argument("--snapshot")
    args = parser.parse_args(argv)
    try:
        probe(args.wait_seconds, args.snapshot)
    except Failure as error:
        print(json.dumps({"status": "FAIL", "code": str(error)}))
        return 2
    except (OSError, ValueError, KeyError):
        print(json.dumps({"status": "FAIL", "code": "PUBLIC_PROBE_FAILED"}))
        return 2
    print(
        json.dumps(
            {
                "status": "PASS",
                "profile": "public",
                "p0_db_e2e": "NOT_RUN",
                "external_https": "NOT_RUN",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
