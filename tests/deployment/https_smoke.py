"""Opt-in, read-only owner HTTPS smoke. Import/default execution never opens a network socket."""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import re
import ssl
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

TARGET = "https://dit.sunghae.xyz"
HOST = "dit.sunghae.xyz"
RUN = "DITNOW_HTTPS_SMOKE_RUN"
APPROVED = "DITNOW_HTTPS_SMOKE_APPROVED"
TIMEOUT_SECONDS = 5
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_ASSETS = 12
ROUTES = (
    "/app",
    "/app/ai",
    "/api/v1/health",
    "/api/v1/auth/me",
    "/api/v1/me/saved-opportunities",
)
PRIVATE = frozenset(ROUTES[3:])
# Namespace identifiers in production React/SVG code are not network endpoints.
NAMESPACES = frozenset(
    {
        "http://www.w3.org/2000/svg",
        "http://www.w3.org/1999/xlink",
        "http://www.w3.org/1998/Math/MathML",
        "http://www.w3.org/XML/1998/namespace",
    }
)
URL_LITERAL = re.compile(r"[\"'`](https?://[^\"'`\s<>]+|wss?://[^\"'`\s<>]+)[\"'`]")
CSS_URL = re.compile(r"url\(\s*[\"']?([^\s\)\"']+)[\"']?\s*\)", re.IGNORECASE)
JS_IMPORT = re.compile(r"(?:\bfrom\s*|\bimport\s*(?:\(\s*)?)[\"']([^\"']+)[\"']")
CSS_IMPORT = re.compile(r"@import\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
ASSET_SUFFIXES = (
    ".js",
    ".mjs",
    ".css",
    ".svg",
    ".ico",
    ".png",
    ".jpg",
    ".webp",
    ".woff",
    ".woff2",
)
SAFE_CODES = frozenset(
    {
        "URL_REJECTED",
        "BODY_LIMIT",
        "INVALID_TEXT",
        "UNSAFE_ENDPOINT_LITERAL",
        "ASSET_PATH_REJECTED",
        "TLS_ERROR",
        "NETWORK_ERROR",
        "RESPONSE_INVALID",
        "REDIRECT_REJECTED",
        "AUTH_NOT_READY",
        "AUTH_BOUNDARY_FAILED",
        "PRIVATE_CACHE_FAILED",
        "AUTH_BODY_INVALID",
        "HEALTH_INVALID",
        "SPA_INVALID",
        "SPA_RELEASE_MISMATCH",
        "ASSET_LIMIT",
        "ASSET_UNAVAILABLE",
        "ASSET_TYPE_INVALID",
    }
)


class SmokeError(Exception):
    """Only a static code may enter reports; never stringify transport/provider errors."""

    def __init__(self, code: str) -> None:
        super().__init__(code if code in SAFE_CODES else "RESPONSE_INVALID")


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes


def validate_url(value: str) -> str:
    """Exact HTTPS origin, no credentials/query/fragment/port or ambiguous path syntax."""
    if (
        not isinstance(value, str)
        or any(ord(c) < 33 for c in value)
        or any(c in value for c in ("\\", "?", "#"))
    ):
        raise SmokeError("URL_REJECTED")
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.netloc != HOST
            or parsed.query
            or parsed.fragment
        ):
            raise SmokeError("URL_REJECTED")
        path = parsed.path or "/"
        if any(
            segment in {".", ".."} for segment in unquote(path).split("/")
        ) or re.search(r"%(?:2f|5c)", path, re.IGNORECASE):
            raise SmokeError("URL_REJECTED")
    except ValueError:
        raise SmokeError("URL_REJECTED") from None
    return value


def fetch_https(url: str) -> Response:
    """No proxy, cookies, credentials, redirects or retry machinery. Verified system trust."""
    validate_url(url)
    context = ssl.create_default_context()
    connection = http.client.HTTPSConnection(
        HOST, port=443, timeout=TIMEOUT_SECONDS, context=context
    )
    try:
        connection.request(
            "GET",
            urlsplit(url).path or "/",
            headers={
                "Accept": "*/*",
                "User-Agent": "DITNOW-owner-https-smoke/1",
                "Cache-Control": "no-cache",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        body = response.read(MAX_BODY_BYTES + 1)
        if len(body) > MAX_BODY_BYTES:
            raise SmokeError("BODY_LIMIT")
        return Response(
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            body,
        )
    finally:
        connection.close()


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.root = False
        self.modules: list[str] = []
        self.assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if (
            tag == "base"
            or tag == "meta"
            and (values.get("http-equiv") or "").lower() == "refresh"
        ):
            raise SmokeError("SPA_INVALID")
        if tag == "div" and values.get("id") == "root":
            self.root = True
        if tag == "script" and values.get("src"):
            self.assets.append(values["src"])
            if values.get("type") == "module":
                self.modules.append(values["src"])
        if (
            tag == "link"
            and values.get("href")
            and set((values.get("rel") or "").split())
            & {"stylesheet", "modulepreload", "icon"}
        ):
            self.assets.append(values["href"])
        if tag in {"img", "source", "iframe", "video", "audio"} and values.get("src"):
            self.assets.append(values["src"])
        if values.get("srcset"):
            self.assets.extend(
                part.strip().split()[0]
                for part in values["srcset"].split(",")
                if part.strip()
            )
        if values.get("style"):
            self.assets.extend(CSS_URL.findall(values["style"]))
        if values.get("poster"):
            self.assets.append(values["poster"])


def decode(body: bytes) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeError:
        raise SmokeError("INVALID_TEXT") from None


def unsafe_url_literal(value: str) -> bool:
    if value in NAMESPACES:
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if (
            parsed.scheme in {"http", "ws"}
            or parsed.username is not None
            or parsed.password is not None
        ):
            return True
        if host == "localhost" or host.endswith((".localhost", ".local")):
            return True
        try:
            address = ipaddress.ip_address(host)
            if not address.is_global:
                return True
        except ValueError:
            pass
        return parsed.path.startswith("/api/") and parsed.netloc != HOST
    except ValueError:
        return True


def scan_endpoints(text: str) -> None:
    # A bare 'localhost' in a safety allowlist is not a URL and is intentionally ignored.
    if any(
        unsafe_url_literal(match.group(1))
        for match in URL_LITERAL.finditer(text.replace("\\/", "/"))
    ):
        raise SmokeError("UNSAFE_ENDPOINT_LITERAL")


def asset_url(value: str, base: str) -> str | None:
    if value.startswith("data:"):
        return None
    url = urljoin(base, value)
    validate_url(url)
    if not urlsplit(url).path.lower().endswith(ASSET_SUFFIXES):
        raise SmokeError("ASSET_PATH_REJECTED")
    return url


def run_smoke(
    env: Mapping[str, str] | None = None, fetch: Callable[[str], Response] = fetch_https
) -> dict:
    env = os.environ if env is None else env
    report = {
        "status": "NOT_RUN",
        "scope": "public_https_smoke_only",
        "target": TARGET,
        "verified_claim": False,
        "authenticated_crud": "NOT_RUN",
        "deployment_approval": "NOT_VERIFIED",
        "checks": [],
        "requests": 0,
        "assets_checked": 0,
    }
    if env.get(RUN) != "1":
        report["reason"] = "OPT_IN_MISSING"
        return report
    if env.get(APPROVED) != "1":
        report["reason"] = "OWNER_APPROVAL_MISSING"
        return report
    total = 0
    cache: dict[str, Response] = {}

    def get(url: str) -> Response:
        nonlocal total
        validate_url(url)
        if url in cache:
            return cache[url]
        report["requests"] += 1
        try:
            response = fetch(url)
        except ssl.SSLError:
            raise SmokeError("TLS_ERROR") from None
        except SmokeError:
            raise
        except Exception:  # noqa: BLE001 -- transport details must never reach owner reports
            raise SmokeError("NETWORK_ERROR") from None
        if (
            not isinstance(response, Response)
            or not isinstance(response.body, bytes)
            or type(response.status) is not int
            or not isinstance(response.headers, Mapping)
            or not all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in response.headers.items()
            )
        ):
            raise SmokeError("RESPONSE_INVALID")
        total += len(response.body)
        if len(response.body) > MAX_BODY_BYTES or total > MAX_TOTAL_BYTES:
            raise SmokeError("BODY_LIMIT")
        if 300 <= response.status < 400:
            raise SmokeError("REDIRECT_REJECTED")
        cache[url] = response
        return response

    modules: set[str] | None = None
    pending: list[str] = []
    failed = False
    for route in ROUTES:
        try:
            response = get(TARGET + route)
            headers = {key.lower(): value for key, value in response.headers.items()}
            if route in PRIVATE:
                if response.status != 401:
                    raise SmokeError(
                        "AUTH_NOT_READY"
                        if response.status in {404, 503}
                        else "AUTH_BOUNDARY_FAILED"
                    )
                if "no-store" not in {
                    part.strip().lower()
                    for part in headers.get("cache-control", "").split(",")
                }:
                    raise SmokeError("PRIVATE_CACHE_FAILED")
                if (
                    headers.get("content-type", "").split(";")[0].strip().lower()
                    != "application/json"
                ):
                    raise SmokeError("AUTH_BODY_INVALID")
                data = json.loads(decode(response.body))
                if data.get("code") != "UNAUTHORIZED":
                    raise SmokeError("AUTH_BODY_INVALID")
            elif route == "/api/v1/health":
                if (
                    response.status != 200
                    or headers.get("content-type", "").split(";")[0].strip().lower()
                    != "application/json"
                ):
                    raise SmokeError("HEALTH_INVALID")
                data = json.loads(decode(response.body))
                if data.get("data") != {"status": "ok", "service": "ditnow-api"}:
                    raise SmokeError("HEALTH_INVALID")
            else:
                if (
                    response.status != 200
                    or headers.get("content-type", "").split(";")[0].strip().lower()
                    != "text/html"
                ):
                    raise SmokeError("SPA_INVALID")
                text = decode(response.body)
                scan_endpoints(text)
                page = Page()
                page.feed(text)
                if not page.root or not page.modules:
                    raise SmokeError("SPA_INVALID")
                entry = {asset_url(value, TARGET + route) for value in page.modules}
                if None in entry:
                    raise SmokeError("SPA_INVALID")
                if modules is not None and entry != modules:
                    raise SmokeError("SPA_RELEASE_MISMATCH")
                modules = entry
                pending.extend(
                    url
                    for value in page.assets
                    if (url := asset_url(value, TARGET + route)) is not None
                )
            report["checks"].append({"path": route, "status": "PASS"})
        except (SmokeError, ValueError, TypeError, AttributeError) as error:
            failed = True
            report["checks"].append(
                {
                    "path": route,
                    "status": "FAIL",
                    "code": str(error)
                    if isinstance(error, SmokeError)
                    else "RESPONSE_INVALID",
                }
            )

    seen: set[str] = set()
    try:
        while pending:
            url = pending.pop(0)
            if url in seen:
                continue
            if len(seen) >= MAX_ASSETS:
                raise SmokeError("ASSET_LIMIT")
            seen.add(url)
            response = get(url)
            if response.status != 200:
                raise SmokeError("ASSET_UNAVAILABLE")
            report["assets_checked"] += 1
            suffix = urlsplit(url).path.lower()
            content_type = (
                response.headers.get(
                    "content-type", response.headers.get("Content-Type", "")
                )
                .split(";")[0]
                .strip()
                .lower()
            )
            if (
                suffix.endswith((".js", ".mjs"))
                and content_type not in {"application/javascript", "text/javascript"}
                or suffix.endswith(".css")
                and content_type != "text/css"
                or content_type == "text/html"
            ):
                raise SmokeError("ASSET_TYPE_INVALID")
            if suffix.endswith((".js", ".mjs", ".css", ".svg")):
                text = decode(response.body)
                scan_endpoints(text)
                references = (
                    CSS_URL.findall(text) + CSS_IMPORT.findall(text)
                    if suffix.endswith(".css")
                    else JS_IMPORT.findall(text)
                    if suffix.endswith((".js", ".mjs"))
                    else []
                )
                pending.extend(
                    child
                    for value in references
                    if (child := asset_url(value, url)) is not None
                )
        report["checks"].append({"path": "same_origin_assets", "status": "PASS"})
    except (SmokeError, ValueError, TypeError, AttributeError) as error:
        failed = True
        report["checks"].append(
            {
                "path": "same_origin_assets",
                "status": "FAIL",
                "code": str(error)
                if isinstance(error, SmokeError)
                else "RESPONSE_INVALID",
            }
        )
    report["status"] = "FAIL" if failed else "PUBLIC_SMOKE_PASS"
    return report


def main() -> int:
    if len(sys.argv) != 1:
        print(
            json.dumps(
                {
                    "status": "NOT_RUN",
                    "reason": "ARGUMENTS_NOT_ALLOWED",
                    "verified_claim": False,
                }
            )
        )
        return 2
    try:
        report = run_smoke()
    except Exception:  # noqa: BLE001 -- fail closed without printing an unexpected raw exception
        report = {"status": "FAIL", "reason": "SMOKE_FAILED", "verified_claim": False}
    print(json.dumps(report, ensure_ascii=True))
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
