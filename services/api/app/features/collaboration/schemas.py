"""Collaboration request/response DTOs.

Requests forbid extra fields, so client-supplied ``author_id``/``user_id``/``role``/``status``/
``member_count``/``source``/free-text report details are rejected with 400 instead of ignored.
Anonymous-zone responses (comments, search, bookmarks, reports) have no author, user, alias,
profile or department field at all.
"""

import unicodedata
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, Field, StringConstraints

from app.features.collaboration.domain import (
    ANONYMOUS_DISPLAY_NAME,
    COMMENT_MAX,
    COMMENT_MIN,
    GROUP_CAPACITY_MAX,
    GROUP_CAPACITY_MIN,
    GROUP_DESCRIPTION_MAX,
    GROUP_NAME_MAX,
    GROUP_NAME_MIN,
    POLICY_BASIS,
    SEARCH_MAX,
    SEARCH_MIN,
    SPACE_POST_MAX,
    SPACE_POST_MIN,
    GroupKind,
    GroupOrigin,
    GroupRole,
    GroupStatus,
    JoinMode,
    MembershipStatus,
    ReportReason,
    ReportStatus,
    ReportTargetType,
    SourceKind,
)
from app.schemas.common import ApiModel

_MULTILINE = {"\n", "\r", "\t"}
ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


def _no_controls(*, multiline: bool):
    def check(value: str) -> str:
        for char in value:
            if unicodedata.category(char) in {"Cc", "Cf", "Cs", "Co"} and not (
                multiline and char in _MULTILINE
            ):
                raise ValueError("control characters are not allowed")
        return value

    return check


def _text(min_length: int, max_length: int, *, multiline: bool):
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length),
        AfterValidator(_no_controls(multiline=multiline)),
    ]


CommentBody = _text(COMMENT_MIN, COMMENT_MAX, multiline=True)
SearchText = _text(SEARCH_MIN, SEARCH_MAX, multiline=False)
GroupName = _text(GROUP_NAME_MIN, GROUP_NAME_MAX, multiline=False)
GroupDescription = _text(0, GROUP_DESCRIPTION_MAX, multiline=True)
SpaceBody = _text(SPACE_POST_MIN, SPACE_POST_MAX, multiline=True)
Revision = Annotated[int, Field(ge=1, strict=True)]
OpaqueId = Annotated[str, StringConstraints(pattern=ID_PATTERN)]


# ---------------------------------------------------------------- requests


class CommentCreate(ApiModel):
    body: CommentBody


class CommentUpdate(ApiModel):
    revision: Revision
    body: CommentBody


class ReportCreate(ApiModel):
    """Reason enum only; there is deliberately no free-text field."""

    target_type: ReportTargetType
    target_id: OpaqueId
    reason: ReportReason


class GroupCreate(ApiModel):
    kind: GroupKind
    name: GroupName
    description: GroupDescription = ""
    join_mode: JoinMode = JoinMode.APPROVAL
    capacity: Annotated[int, Field(ge=GROUP_CAPACITY_MIN, le=GROUP_CAPACITY_MAX, strict=True)]


class JoinDecision(ApiModel):
    decision: Literal["approve", "reject"]
    revision: Revision


class MembershipLeave(ApiModel):
    revision: Revision


class SpacePostCreate(ApiModel):
    body: SpaceBody


# ---------------------------------------------------------------- responses


class Page[T](ApiModel):
    items: list[T]
    limit: int
    offset: int
    has_more: bool


class PostSummary(ApiModel):
    """Public projection of a community anonymous post; reuses its ID, never its author.

    ``bookmarked`` is only the caller's own bookmark state for this post.
    """

    id: str
    display_name: str = ANONYMOUS_DISPLAY_NAME
    title: str
    excerpt: str
    comment_count: int
    bookmarked: bool
    created_at: AwareDatetime


class CommentPublic(ApiModel):
    id: str
    post_id: str
    display_name: str = ANONYMOUS_DISPLAY_NAME
    body: str
    is_mine: bool
    revision: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class DeletedResource(ApiModel):
    id: str
    deleted: bool = True


class BookmarkPublic(ApiModel):
    post: PostSummary
    bookmarked_at: AwareDatetime


class BookmarkState(ApiModel):
    post_id: str
    bookmarked: bool


class ReportPublic(ApiModel):
    """Reporter's own receipt. Never includes the target's author or reviewer details."""

    id: str
    target_type: ReportTargetType
    target_id: str
    reason: ReportReason
    status: ReportStatus
    created_at: AwareDatetime


class SourcePublic(ApiModel):
    kind: SourceKind
    url: str | None
    checked_at: datetime | None


class ProfileName(ApiModel):
    display_name: str | None


class MyMembership(ApiModel):
    id: str
    role: GroupRole
    status: MembershipStatus
    revision: int


class GroupPublic(ApiModel):
    id: str
    kind: GroupKind
    name: str
    description: str
    join_mode: JoinMode
    capacity: int
    member_count: int
    status: GroupStatus
    origin: GroupOrigin
    source: SourcePublic
    policy_basis: Literal["DEMO_DESIGN_DEFAULT"] = POLICY_BASIS
    leader: ProfileName
    my_membership: MyMembership | None
    revision: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class JoinRequestPublic(ApiModel):
    """Leader-only view of a join request: public activity name, no other profile data."""

    id: str
    group_id: str
    applicant: ProfileName
    status: MembershipStatus
    revision: int
    created_at: AwareDatetime


class SpacePostPublic(ApiModel):
    id: str
    group_id: str
    author: ProfileName
    is_mine: bool
    body: str
    revision: int
    created_at: AwareDatetime
