"""Community request/response DTOs.

Request models inherit ``extra="forbid"`` so client-supplied ``author_id``/``owner_id``/
``status``/``accepted_count`` are rejected with the common 400 envelope instead of ignored.
Anonymous post responses have no author, user, profile, department or email fields at all.
"""

import unicodedata
from typing import Annotated, Self

from pydantic import AfterValidator, AwareDatetime, Field, StringConstraints, model_validator

from app.features.community.domain import (
    ANONYMOUS_DISPLAY_NAME,
    BODY_MAX,
    BODY_MIN,
    CAPACITY_MAX,
    CAPACITY_MIN,
    FIELD_MAX,
    ROLE_MAX,
    ROLES_MAX,
    TITLE_MAX,
    TITLE_MIN,
    PostStatus,
    RecruitmentStatus,
)
from app.schemas.common import ApiModel

_MULTILINE_ALLOWED = {"\n", "\r", "\t"}


def _reject_controls(*, multiline: bool):
    def check(value: str) -> str:
        for char in value:
            if unicodedata.category(char) in {"Cc", "Cf", "Cs", "Co"} and not (
                multiline and char in _MULTILINE_ALLOWED
            ):
                raise ValueError("control characters are not allowed")
        return value

    return check


Title = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=TITLE_MIN, max_length=TITLE_MAX),
    AfterValidator(_reject_controls(multiline=False)),
]
Body = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=BODY_MIN, max_length=BODY_MAX),
    AfterValidator(_reject_controls(multiline=True)),
]
ShortLabel = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=FIELD_MAX),
    AfterValidator(_reject_controls(multiline=False)),
]
RoleName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=ROLE_MAX),
    AfterValidator(_reject_controls(multiline=False)),
]
Capacity = Annotated[int, Field(ge=CAPACITY_MIN, le=CAPACITY_MAX, strict=True)]
Revision = Annotated[int, Field(ge=1, strict=True)]
# Only an opaque source ID of an approved opportunity is accepted; never a URL or free text.
OpportunityId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Roles = Annotated[list[RoleName], Field(min_length=1, max_length=ROLES_MAX)]


def _unique_roles(roles: list[str] | None) -> None:
    if roles is not None and len({role.casefold() for role in roles}) != len(roles):
        raise ValueError("roles must be unique")


def _forbid_explicit_null(model: ApiModel, names: tuple[str, ...]) -> None:
    provided = [name for name in names if name in model.model_fields_set]
    if not provided:
        raise ValueError("at least one field is required")
    if any(getattr(model, name) is None for name in provided):
        raise ValueError("fields cannot be null")


# ---------------------------------------------------------------- anonymous posts (FR-COM-001)


class AnonymousPostCreate(ApiModel):
    title: Title
    body: Body


class AnonymousPostUpdate(ApiModel):
    revision: Revision
    title: Title | None = None
    body: Body | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        _forbid_explicit_null(self, ("title", "body"))
        return self


class AnonymousPostPublic(ApiModel):
    id: str
    display_name: str = ANONYMOUS_DISPLAY_NAME
    title: str
    body: str
    status: PostStatus
    comment_count: int
    is_mine: bool
    revision: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class AnonymousPostPage(ApiModel):
    items: list[AnonymousPostPublic]
    limit: int
    offset: int
    has_more: bool


class DeletedResource(ApiModel):
    id: str
    deleted: bool = True


# ---------------------------------------------------------------- recruitments (FR-COM-004)


class RecruitmentCreate(ApiModel):
    title: Title
    body: Body
    field: ShortLabel
    roles: Roles
    capacity: Capacity
    deadline_at: AwareDatetime
    opportunity_id: OpportunityId | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        _unique_roles(self.roles)
        return self


class RecruitmentUpdate(ApiModel):
    revision: Revision
    title: Title | None = None
    body: Body | None = None
    field: ShortLabel | None = None
    roles: Roles | None = None
    capacity: Capacity | None = None
    deadline_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        _forbid_explicit_null(self, ("title", "body", "field", "roles", "capacity", "deadline_at"))
        _unique_roles(self.roles)
        return self


class RecruitmentClose(ApiModel):
    revision: Revision


class PublicProfile(ApiModel):
    """Allowed real-name activity profile fields only (no email, student number, department)."""

    display_name: str | None


class RecruitmentPublic(ApiModel):
    id: str
    owner: PublicProfile
    is_mine: bool
    title: str
    body: str
    field: str
    roles: list[str]
    capacity: int
    accepted_count: int
    deadline_at: AwareDatetime
    status: RecruitmentStatus
    opportunity_id: str | None
    revision: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class RecruitmentPage(ApiModel):
    items: list[RecruitmentPublic]
    limit: int
    offset: int
    has_more: bool
