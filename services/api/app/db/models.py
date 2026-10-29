"""P0 logical records (FR-AUTH/COM/OPP); no account provisioning or access grants.

UUIDs use portable CHAR(32); timestamps are stored as UTC without a database timezone.
MariaDB runtime/version/privilege tests remain required before deployment.
"""

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.dialects.mysql import BINARY, DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.schemas.common import utc_now


class UTCDateTime(TypeDecorator[datetime]):
    """Reject naive writes; normalize both MariaDB and local test results to aware UTC."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name in {"mysql", "mariadb"}:
            return dialect.type_descriptor(DATETIME(fsp=6))
        return dialect.type_descriptor(DateTime())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone-aware timestamps are required")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    type_annotation_map = {UUID: Uuid(native_uuid=False), datetime: UTCDateTime()}


class RecordColumns:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)
    source_kind: Mapped[str] = mapped_column(String(20), default="DEMO")
    source_url: Mapped[str | None] = mapped_column(String(2048))
    checked_at: Mapped[datetime | None]


def subject_digest(issuer: str, subject: str) -> bytes:
    """Length framing preserves exact, case-sensitive identity without oversized MariaDB indexes.

    The digest is only a uniqueness/index key; every identity lookup also compares original values.
    A collision therefore refuses a binding instead of selecting another user's identity.
    """
    parts = [value.encode("utf-8") for value in (issuer, subject)]
    return hashlib.sha256(b"".join(len(part).to_bytes(8, "big") + part for part in parts)).digest()


class IdentityRow(RecordColumns, Base):
    __tablename__ = "identities"
    __table_args__ = (
        CheckConstraint("status IN ('pending','active','disabled')", name="ck_identity_status"),
        CheckConstraint("revision > 0", name="ck_identity_revision"),
        UniqueConstraint("binding_digest", name="uq_identity_binding_digest"),
    )
    issuer: Mapped[str] = mapped_column(String(2048))
    subject: Mapped[str] = mapped_column(String(512))
    binding_digest: Mapped[bytes] = mapped_column(
        LargeBinary(32).with_variant(BINARY(32), "mysql", "mariadb")
    )
    status: Mapped[str] = mapped_column(String(16), default="pending")


@event.listens_for(IdentityRow, "before_insert")
@event.listens_for(IdentityRow, "before_update")
def _set_binding_digest(mapper, connection, target):
    target.binding_digest = subject_digest(target.issuer, target.subject)


class ProfileRow(Base):
    __tablename__ = "profiles"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identities.id", ondelete="RESTRICT"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(100))
    source_kind: Mapped[str] = mapped_column(String(20), default="DEMO")
    # No editable department/year/role copies: approved memberships/assignments are authoritative.


class DepartmentRow(RecordColumns, Base):
    __tablename__ = "departments"
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class AcademicMembershipRow(RecordColumns, Base):
    __tablename__ = "academic_memberships"
    __table_args__ = (
        CheckConstraint("academic_year > 0", name="ck_membership_year"),
        CheckConstraint("status IN ('pending','active','inactive')", name="ck_membership_status"),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_membership_period"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("identities.id", ondelete="RESTRICT"))
    department_id: Mapped[UUID] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"))
    academic_year: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default="pending")
    valid_from: Mapped[datetime]
    valid_to: Mapped[datetime | None]


class RoleAssignmentRow(RecordColumns, Base):
    __tablename__ = "role_assignments"
    __table_args__ = (
        CheckConstraint("role IN ('student','professor','assistant','admin')", name="ck_role_kind"),
        CheckConstraint("status IN ('pending','active','revoked')", name="ck_role_status"),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_role_period"),
        CheckConstraint(
            "(scope_type = 'platform' AND scope_id IS NULL) OR "
            "(scope_type IN ('department','course_offering') AND scope_id IS NOT NULL)",
            name="ck_role_scope",
        ),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("identities.id", ondelete="RESTRICT"))
    role: Mapped[str] = mapped_column(String(16))
    scope_type: Mapped[str] = mapped_column(String(32))
    scope_id: Mapped[UUID | None]
    status: Mapped[str] = mapped_column(String(16), default="pending")
    valid_from: Mapped[datetime]
    valid_to: Mapped[datetime | None]


class AnonymousPostRow(RecordColumns, Base):
    __tablename__ = "anonymous_posts_private"
    __table_args__ = (
        CheckConstraint("status IN ('active','hidden','deleted')", name="ck_post_status"),
        CheckConstraint("revision > 0", name="ck_post_revision"),
    )
    author_id: Mapped[UUID] = mapped_column(ForeignKey("identities.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")


class OpportunityRow(RecordColumns, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint(
            "submission_mode IN ('external_document_submission','external_link','info_only')",
            name="ck_opportunity_submission_mode",
        ),
        CheckConstraint("source_kind IN ('OFFICIAL_PUBLIC','DEMO','USER_DEMO')", name="ck_origin"),
        CheckConstraint(
            "source_kind != 'OFFICIAL_PUBLIC' OR "
            "(source_url IS NOT NULL AND checked_at IS NOT NULL)",
            name="ck_official_origin",
        ),
    )
    kind: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(120))
    organization: Mapped[str] = mapped_column(String(200), default="")
    eligibility: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    target_scope: Mapped[dict] = mapped_column(JSON, default=lambda: {"level": "school"})
    files: Mapped[list] = mapped_column(JSON, default=list)
    apply_starts_at: Mapped[datetime | None]
    deadline_at: Mapped[datetime | None]
    original_url: Mapped[str | None] = mapped_column(String(2048))
    submission_mode: Mapped[str] = mapped_column(String(40))
    destination: Mapped[str | None] = mapped_column(String(1000))
    source_kind: Mapped[str] = mapped_column(String(20), default="DEMO")
    source_url: Mapped[str | None] = mapped_column(String(2048))
    checked_at: Mapped[datetime | None]


class RecruitmentRow(RecordColumns, Base):
    __tablename__ = "recruitments"
    __table_args__ = (
        CheckConstraint("capacity >= 2", name="ck_recruitment_capacity"),
        CheckConstraint("status IN ('open','closed','cancelled')", name="ck_recruitment_status"),
        CheckConstraint("revision > 0", name="ck_recruitment_revision"),
        CheckConstraint(
            "accepted_count >= 0 AND accepted_count + 1 <= capacity", name="ck_recruitment_seats"
        ),
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("identities.id", ondelete="RESTRICT"))
    opportunity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    field: Mapped[str] = mapped_column(String(30), default="")
    roles: Mapped[list] = mapped_column(JSON, default=list)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    capacity: Mapped[int]
    deadline_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(16), default="open")


class SavedOpportunityRow(RecordColumns, Base):
    __tablename__ = "saved_opportunities"
    __table_args__ = (
        UniqueConstraint("user_id", "opportunity_id", name="uq_saved_user_opportunity"),
        CheckConstraint(
            "status IN ('interested','preparing','self_reported_submitted','closed')",
            name="ck_saved_status",
        ),
        CheckConstraint(
            "status != 'self_reported_submitted' OR self_reported_submitted_at IS NOT NULL",
            name="ck_saved_submission_date",
        ),
        CheckConstraint("revision > 0", name="ck_saved_revision"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("identities.id", ondelete="RESTRICT"))
    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(32), default="interested")
    memo: Mapped[str] = mapped_column(Text, default="")
    self_reported_submitted_at: Mapped[datetime | None]


class OpportunityCheckItemRow(RecordColumns, Base):
    __tablename__ = "opportunity_check_items"
    __table_args__ = (
        CheckConstraint("sort_order >= 0", name="ck_check_order"),
        CheckConstraint("revision > 0", name="ck_check_revision"),
        UniqueConstraint("saved_opportunity_id", "sort_order", name="uq_check_parent_order"),
    )
    saved_opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("saved_opportunities.id", ondelete="RESTRICT")
    )
    text: Mapped[str] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(default=0)
    completed_at: Mapped[datetime | None]


class AuditLogRow(RecordColumns, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "resource_kind != 'anonymous_post' OR actor_id IS NULL OR entity_id IS NULL",
            name="ck_audit_no_anonymous_mapping",
        ),
    )
    event: Mapped[str] = mapped_column(String(100))
    resource_kind: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("identities.id", ondelete="RESTRICT"))
    entity_id: Mapped[UUID | None]


class AnonymousPostPublicRow(RecordColumns, Base):
    """Separate public read model. Author and profile fields are intentionally absent."""

    __tablename__ = "anonymous_posts_public"
    __table_args__ = (
        CheckConstraint("status IN ('active','hidden','deleted')", name="ck_public_post_status"),
        CheckConstraint("revision > 0", name="ck_public_post_revision"),
    )
    id: Mapped[UUID] = mapped_column(
        ForeignKey("anonymous_posts_private.id", ondelete="RESTRICT"), primary_key=True
    )
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    comment_count: Mapped[int] = mapped_column(Integer, default=0)


class CommunityClaimRow(Base):
    __tablename__ = "community_idempotency_claims"
    namespace_digest: Mapped[bytes] = mapped_column(
        LargeBinary(32).with_variant(BINARY(32), "mysql", "mariadb"), primary_key=True
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("identities.id", ondelete="RESTRICT"))
    method: Mapped[str] = mapped_column(String(8))
    canonical_path: Mapped[str] = mapped_column(String(128))
    key: Mapped[str] = mapped_column(String(128))
    body_digest: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[UUID]


class CheckClaimRow(Base):
    __tablename__ = "opportunity_check_idempotency"
    namespace_digest: Mapped[bytes] = mapped_column(
        LargeBinary(32).with_variant(BINARY(32), "mysql", "mariadb"), primary_key=True
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("identities.id", ondelete="RESTRICT"))
    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="RESTRICT")
    )
    operation: Mapped[str] = mapped_column(String(128))
    key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    check_id: Mapped[UUID]
    original_saved_id: Mapped[UUID]
    tombstone: Mapped[bool] = mapped_column(Boolean, default=False)


class SavedStatusEventRow(Base):
    __tablename__ = "saved_opportunity_status_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    saved_id: Mapped[UUID]
    user_id: Mapped[UUID] = mapped_column(ForeignKey("identities.id", ondelete="RESTRICT"))
    from_status: Mapped[str] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime]
    correction: Mapped[bool] = mapped_column(Boolean)


class RecruitmentApplicationRow(RecordColumns, Base):
    """P1 ledger proposal; no application/approval HTTP endpoint is activated."""

    __tablename__ = "recruitment_applications"
    __table_args__ = (
        UniqueConstraint("recruitment_id", "applicant_id", name="uq_recruitment_applicant"),
        CheckConstraint(
            "status IN ('pending','accepted','rejected','withdrawn')", name="ck_application_status"
        ),
    )
    recruitment_id: Mapped[UUID] = mapped_column(ForeignKey("recruitments.id", ondelete="RESTRICT"))
    applicant_id: Mapped[UUID] = mapped_column(ForeignKey("identities.id", ondelete="RESTRICT"))
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")


# The initial DDL is a proposal for a transactional, Unicode-capable engine. No schema is applied.
for _table in Base.metadata.tables.values():
    for _dialect in ("mysql", "mariadb"):
        _table.dialect_options[_dialect]["engine"] = "InnoDB"
        _table.dialect_options[_dialect]["charset"] = "utf8mb4"
        _table.dialect_options[_dialect]["collate"] = "utf8mb4_unicode_ci"
