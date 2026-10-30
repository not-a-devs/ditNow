"""Offline configuration diagnostic, never deployment/readiness approval or a network probe.

Reuse Settings and the existing DB report. No application, SDK client or engine is constructed;
no secret file is read and no server, migration or seed is started. Settings still constructs
its empty dotenv/secret sources. These conservative production diagnostics change no policy.
"""

import argparse
import json
import math
from dataclasses import asdict, dataclass
from typing import Literal
from urllib.parse import urlsplit

from app.core.config import Settings
from app.core.db_connection import configuration_report

type Profile = Literal["public", "p0"]


@dataclass(frozen=True)
class PreflightReport:
    configuration: Literal["PASS", "FAIL"]
    profile: Profile | None
    codes: tuple[str, ...]
    # These deliberately remain unverified even when all local configuration checks pass.
    deployment: Literal["NOT_RUN"] = "NOT_RUN"
    db_connection: Literal["NOT_RUN"] = "NOT_RUN"
    db_schema: Literal["NOT_RUN"] = "NOT_RUN"
    db_grants: Literal["NOT_RUN"] = "NOT_RUN"
    db_certificate_pin: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"
    identity_approvals: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"
    ingress_spa_https: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"
    host_proxy_workers: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"
    llm_approval_and_call: Literal["NOT_RUN"] = "NOT_RUN"


def inspect_settings(settings: Settings, profile: Profile) -> PreflightReport:
    if profile not in {"public", "p0"}:
        raise ValueError("Invalid profile")
    codes: list[str] = []
    if settings.environment != "production":
        codes.append("PRODUCTION_ENVIRONMENT_REQUIRED")
    if settings.docs_enabled:
        codes.append("DOCS_EXPOSURE_REVIEW_REQUIRED")
    # Empty origins support same-origin proxy deployment; they do not prove its existence.
    if any(urlsplit(origin).scheme != "https" for origin in settings.cors_origins):
        codes.append("HTTPS_CORS_REVIEW_REQUIRED")
    if settings.database_url is not None:
        codes.append("LEGACY_DATABASE_URL_UNSUPPORTED")
    if settings.ask_rate_limit_per_min <= 0:
        codes.append("POSITIVE_RATE_LIMIT_REQUIRED")
    db = configuration_report(settings)
    if profile == "p0":
        if not settings.p0_runtime_enabled:
            codes.append("P0_RUNTIME_DISABLED")
        if not db.configured:
            codes.append("P0_DATABASE_CONFIGURATION_MISSING")
        if not settings.p0_schema_approved:
            codes.append("P0_SCHEMA_ATTESTATION_MISSING")
        if not settings.p0_identity_approval_ids:
            codes.append("P0_IDENTITY_APPROVAL_PINS_MISSING")
        elif len(set(settings.p0_identity_approval_ids)) != len(settings.p0_identity_approval_ids):
            codes.append("P0_IDENTITY_APPROVAL_PINS_DUPLICATED")
    elif settings.p0_runtime_enabled:
        codes.append("PUBLIC_PROFILE_HAS_P0_RUNTIME")

    provider = settings.llm_provider
    model, base = settings.llm_model.strip(), settings.llm_base_url.strip()
    has_key = bool(settings.llm_api_key.get_secret_value())
    if provider is None:
        if model or base or has_key:
            codes.append("ORPHAN_LLM_CONFIGURATION")
    else:
        if not model:
            codes.append("LLM_MODEL_MISSING")
        if provider in {"openai", "anthropic"} and not has_key:
            codes.append("LLM_API_KEY_MISSING")
        # The existing compatible client supports approved keyless servers; do not invent
        # a mandatory key here. The endpoint/cost/data approval remains external and NOT_RUN.
        if provider == "openai_compatible" and not base:
            codes.append("LLM_COMPATIBLE_BASE_URL_MISSING")
        if not math.isfinite(settings.llm_timeout_sec) or settings.llm_timeout_sec <= 0:
            codes.append("POSITIVE_FINITE_LLM_TIMEOUT_REQUIRED")
    return PreflightReport("FAIL" if codes else "PASS", profile, tuple(codes))


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message):
        # argparse's normal diagnostic can echo unknown argv, including an accidental secret.
        raise ValueError("Invalid arguments")


def main(argv=None) -> int:
    parser = SafeArgumentParser(
        description="Offline configuration only; deployment NOT_RUN", allow_abbrev=False
    )
    parser.add_argument("--profile", choices=("public", "p0"), required=True)
    try:
        args = parser.parse_args(argv)
    except ValueError:
        report = PreflightReport("FAIL", None, ("INVALID_ARGUMENTS",))
    else:
        try:
            report = inspect_settings(Settings(), args.profile)
        except (ValueError, OSError):
            # Never emit exception messages, input values, settings dumps or credential paths.
            report = PreflightReport("FAIL", args.profile, ("SETTINGS_INVALID",))
    print(json.dumps(asdict(report)))
    return 0 if report.configuration == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
