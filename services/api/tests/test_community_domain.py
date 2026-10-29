"""Pure domain/DTO tests for FR-COM-001/004/005 rules (TC-V1-COM-001/004/005 unit level)."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.errors import ApiError
from app.features.community.domain import (
    ApplicationStatus,
    CommunityActor,
    Recruitment,
    RecruitmentStatus,
    check_accept,
    check_application,
    effective_status,
    has_open_seat,
    require_member,
    transition_application,
    transition_recruitment,
)
from app.features.community.schemas import (
    AnonymousPostCreate,
    AnonymousPostPublic,
    AnonymousPostUpdate,
    PublicProfile,
    RecruitmentCreate,
    RecruitmentPublic,
    RecruitmentUpdate,
)
from app.schemas.common import ErrorCode

NOW = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)
IDENTITY_FIELDS = {
    "author",
    "author_id",
    "user",
    "user_id",
    "owner_id",
    "email",
    "department",
    "grade",
    "student_number",
    "identity",
}


def recruitment(**overrides) -> Recruitment:
    values = dict(
        id="r1",
        owner_id="owner",
        title="해커톤 팀원",
        body="함께해요",
        field="개발",
        roles=("백엔드",),
        capacity=3,
        accepted_count=0,
        deadline_at=NOW + timedelta(days=3),
        status=RecruitmentStatus.OPEN,
        opportunity_id=None,
        revision=1,
        created_at=NOW,
        updated_at=NOW,
    )
    values.update(overrides)
    return Recruitment(**values)


def test_public_dtos_have_no_identity_fields():
    assert IDENTITY_FIELDS.isdisjoint(AnonymousPostPublic.model_fields)
    assert IDENTITY_FIELDS.isdisjoint(RecruitmentPublic.model_fields)
    assert set(PublicProfile.model_fields) == {"display_name"}


def test_anonymous_display_name_is_fixed():
    assert AnonymousPostPublic.model_fields["display_name"].default == "익명"


@pytest.mark.parametrize("field", ["author_id", "user_id", "status", "revision", "is_mine"])
def test_post_create_rejects_injected_server_fields(field):
    with pytest.raises(ValidationError):
        AnonymousPostCreate.model_validate({"title": "제목입니다", "body": "본문", field: "x"})


@pytest.mark.parametrize(
    "title,body,ok",
    [
        ("가나", "a", True),
        ("가" * 120, "b" * 5000, True),
        ("가", "a", False),
        ("  가  ", "a", False),
        ("가" * 121, "a", False),
        ("제목", "", False),
        ("제목", "   ", False),
        ("제목", "b" * 5001, False),
        ("제목\n줄바꿈", "a", False),
        ("제목\x00", "a", False),
        ("제목‮", "a", False),
        ("제목", "여러\n줄\t본문", True),
        (123, "a", False),
    ],
)
def test_post_title_body_boundaries(title, body, ok):
    if ok:
        model = AnonymousPostCreate(title=title, body=body)
        assert model.title == title.strip()
    else:
        with pytest.raises(ValidationError):
            AnonymousPostCreate(title=title, body=body)


def test_post_update_requires_change_and_forbids_null():
    with pytest.raises(ValidationError):
        AnonymousPostUpdate(revision=1)
    with pytest.raises(ValidationError):
        AnonymousPostUpdate.model_validate({"revision": 1, "title": None})
    with pytest.raises(ValidationError):
        AnonymousPostUpdate.model_validate({"revision": "1", "title": "제목수정"})
    assert AnonymousPostUpdate(revision=2, body="수정").model_fields_set == {"revision", "body"}


def valid_recruitment(**overrides):
    values = dict(
        title="공모전 팀원 모집",
        body="설명",
        field="개발",
        roles=["프론트엔드"],
        capacity=4,
        deadline_at=(NOW + timedelta(days=1)).isoformat(),
    )
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    "overrides",
    [
        {"capacity": 1},
        {"capacity": 21},
        {"capacity": "3"},
        {"capacity": 2.5},
        {"roles": []},
        {"roles": ["a"] * 11},
        {"roles": ["디자인", "디자인"]},
        {"roles": ["Dev", "dev"]},
        {"deadline_at": "2026-11-01T00:00:00"},
        {"opportunity_id": "https://evil.test/x"},
        {"field": ""},
        {"owner_id": "someone"},
        {"status": "closed"},
        {"accepted_count": 5},
    ],
)
def test_recruitment_create_rejects_invalid(overrides):
    with pytest.raises(ValidationError):
        RecruitmentCreate.model_validate(valid_recruitment(**overrides))


def test_recruitment_create_accepts_boundaries():
    assert RecruitmentCreate.model_validate(valid_recruitment(capacity=2)).capacity == 2
    model = RecruitmentCreate.model_validate(valid_recruitment(capacity=20, opportunity_id="opp_1"))
    assert model.opportunity_id == "opp_1"


def test_recruitment_update_forbids_status_and_null():
    with pytest.raises(ValidationError):
        RecruitmentUpdate.model_validate({"revision": 1, "status": "closed"})
    with pytest.raises(ValidationError):
        RecruitmentUpdate.model_validate({"revision": 1, "capacity": None})


def test_require_member():
    with pytest.raises(ApiError) as exc:
        require_member(None)
    assert exc.value.code is ErrorCode.UNAUTHORIZED
    for actor in (CommunityActor("u", False), CommunityActor("", True)):
        with pytest.raises(ApiError) as exc:
            require_member(actor)
        assert exc.value.code is ErrorCode.FORBIDDEN
    assert require_member(CommunityActor("u", True)).user_id == "u"


def test_capacity_counts_recruiter():
    assert has_open_seat(capacity=2, accepted_count=0)
    assert not has_open_seat(capacity=2, accepted_count=1)
    assert has_open_seat(capacity=3, accepted_count=1)


def test_deadline_uses_server_time():
    row = recruitment(deadline_at=NOW)
    assert effective_status(row, NOW - timedelta(seconds=1)) is RecruitmentStatus.OPEN
    assert effective_status(row, NOW) is RecruitmentStatus.CLOSED
    assert effective_status(recruitment(status=RecruitmentStatus.CANCELLED), NOW) is (
        RecruitmentStatus.CANCELLED
    )


@pytest.mark.parametrize(
    "start,target,ok",
    [
        (RecruitmentStatus.OPEN, RecruitmentStatus.CLOSED, True),
        (RecruitmentStatus.OPEN, RecruitmentStatus.CANCELLED, True),
        (RecruitmentStatus.CLOSED, RecruitmentStatus.OPEN, False),
        (RecruitmentStatus.CLOSED, RecruitmentStatus.CANCELLED, False),
        (RecruitmentStatus.CANCELLED, RecruitmentStatus.OPEN, False),
        (RecruitmentStatus.OPEN, RecruitmentStatus.OPEN, False),
    ],
)
def test_recruitment_transitions(start, target, ok):
    row = recruitment(status=start)
    if ok:
        moved = transition_recruitment(row, target, NOW)
        assert (moved.status, moved.revision) == (target, 2)
    else:
        with pytest.raises(ApiError) as exc:
            transition_recruitment(row, target, NOW)
        assert exc.value.code is ErrorCode.CONFLICT


def test_application_transitions():
    transition_application(ApplicationStatus.PENDING, ApplicationStatus.ACCEPTED)
    transition_application(ApplicationStatus.PENDING, ApplicationStatus.WITHDRAWN)
    for start in (ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED):
        with pytest.raises(ApiError):
            transition_application(start, ApplicationStatus.PENDING)


@pytest.mark.parametrize(
    "row,applicant",
    [
        (recruitment(), "owner"),
        (recruitment(capacity=2, accepted_count=1), "other"),
        (recruitment(status=RecruitmentStatus.CLOSED), "other"),
        (recruitment(deadline_at=NOW), "other"),
    ],
)
def test_application_precheck_rejects(row, applicant):
    with pytest.raises(ApiError) as exc:
        check_application(row, applicant, NOW)
    assert exc.value.code is ErrorCode.CONFLICT


def test_accept_precheck_allows_last_seat_once():
    row = recruitment(capacity=3, accepted_count=1)
    check_accept(row, NOW)
    with pytest.raises(ApiError):
        check_accept(recruitment(capacity=3, accepted_count=2), NOW)
