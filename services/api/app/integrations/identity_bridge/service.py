"""Explicitly approved subject mapping plus current DEMO student qualification.

No route/dependency registration. Per-resource policy MUST run again in its operation UOW.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from pydantic import SecretStr

from app.core.errors import ApiError
from app.schemas.common import ErrorCode

from .contracts import ApprovedMapping, BridgePrincipal, IdentityLedger, LegacyTokenVerifier


def _aware(value: datetime) -> bool:
    return (
        isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
    )


def _current(start: datetime, end: datetime | None, now: datetime) -> bool:
    return (
        _aware(start)
        and (end is None or (_aware(end) and start < end))
        and start <= now
        and (end is None or now < end)
    )


def _approved(mapping: ApprovedMapping, now: datetime) -> bool:
    return (
        mapping.active is True
        and isinstance(mapping.user_id, UUID)
        and mapping.user_id.int != 0
        and isinstance(mapping.approved_by, UUID)
        and mapping.approved_by.int != 0
        and mapping.revoked_at is None
        and mapping.legacy_source_kind == "DEMO"
        and _aware(mapping.approved_at)
        and mapping.approved_at <= now
    )


class IdentityBridge:
    def __init__(
        self,
        *,
        issuer: str | None = None,
        verifier: LegacyTokenVerifier | None = None,
        ledger: IdentityLedger | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._issuer = issuer
        self._verifier = verifier
        self._ledger = ledger
        self._clock = clock

    async def resolve_student(self, token: SecretStr) -> BridgePrincipal:
        """Return only an internal UUID, with no cached claims or role elevation.

        Invalid token=401, absent/ineligible/ambiguous approval=403, unconfigured/fault=503.
        Token validity is checked on every call before the common-ledger UOW; revocation can
        race a request already underway, so sensitive operations must recheck their current
        authority in the operation UOW. This is not a distributed atomic auth implementation.
        """
        if (
            not self._issuer
            or len(self._issuer) > 2048
            or any(char.isspace() or ord(char) < 32 for char in self._issuer)
            or self._verifier is None
            or self._ledger is None
        ):
            raise ApiError(ErrorCode.UNAVAILABLE)
        if not isinstance(token, SecretStr):
            raise ApiError(ErrorCode.UNAUTHORIZED)
        raw = token.get_secret_value()
        if not 1 <= len(raw) <= 512 or any(char.isspace() or ord(char) < 32 for char in raw):
            raise ApiError(ErrorCode.UNAUTHORIZED)
        try:
            subject = await self._verifier.verify(token)
            if not isinstance(subject, str) or not 1 <= len(subject) <= 20:
                raise ApiError(ErrorCode.UNAUTHORIZED)
            now = self._clock()
            if not _aware(now):
                raise ApiError(ErrorCode.UNAVAILABLE)
            async with self._ledger.transaction() as tx:
                candidates = await tx.mappings_for_subject(self._issuer, subject)
                if len(candidates) != 1:
                    raise ApiError(ErrorCode.FORBIDDEN)
                mapping = candidates[0]
                if (
                    mapping.issuer != self._issuer
                    or mapping.subject != subject
                    or not _approved(mapping, now)
                ):
                    raise ApiError(ErrorCode.FORBIDDEN)
                # Reject many legacy subjects mapping to one UUID, including hash/collation
                # aliases. The adapter must enforce forward and reverse unique approvals.
                reverse = await tx.mappings_for_user(mapping.user_id)
                if len(reverse) != 1 or reverse[0] != mapping:
                    raise ApiError(ErrorCode.FORBIDDEN)
                identity = await tx.identity(mapping.user_id)
                profile = await tx.profile(mapping.user_id)
                if (
                    identity is None
                    or identity.user_id != mapping.user_id
                    or identity.issuer != self._issuer
                    or identity.subject != subject
                    or identity.status != "active"
                    or identity.source_kind != "DEMO"
                    or profile is None
                    or profile.user_id != mapping.user_id
                    or profile.source_kind != "DEMO"
                ):
                    raise ApiError(ErrorCode.FORBIDDEN)
                memberships = [
                    item
                    for item in await tx.memberships(mapping.user_id)
                    if item.user_id == mapping.user_id
                    and item.status == "active"
                    and isinstance(item.department_id, UUID)
                    and item.department_id.int != 0
                    and type(item.academic_year) is int
                    and item.academic_year > 0
                    and _current(item.valid_from, item.valid_to, now)
                ]
                if len(memberships) != 1:
                    raise ApiError(ErrorCode.FORBIDDEN)
                department = memberships[0].department_id
                allowed = any(
                    role.user_id == mapping.user_id
                    and role.status == "active"
                    and role.role == "student"
                    and _current(role.valid_from, role.valid_to, now)
                    and (
                        (role.scope_type == "platform" and role.scope_id is None)
                        or (role.scope_type == "department" and role.scope_id == department)
                    )
                    for role in await tx.roles(mapping.user_id)
                )
                if not allowed:
                    raise ApiError(ErrorCode.FORBIDDEN)
                return BridgePrincipal(user_id=mapping.user_id)
        except ApiError:
            raise
        except Exception:
            # No raw driver error, token, subject, or internal-row contents in error/log output.
            raise ApiError(ErrorCode.UNAVAILABLE) from None


def get_identity_bridge() -> IdentityBridge:
    """Inactive seam: an application owner must explicitly inject reviewed dependencies."""
    raise ApiError(ErrorCode.UNAVAILABLE)
