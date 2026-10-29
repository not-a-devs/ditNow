"""FR-OPP-002 deterministic matching + FR-AI-002/003 rule subset (service level, fakes only)."""

from datetime import datetime, timedelta
from uuid import UUID

import pytest
from test_opportunity_matching_support import (
    BODY_SECRET,
    NOW,
    OWNER_SECRET,
    USER_A,
    USER_B,
    USER_C,
    FakeCatalog,
    FakeContexts,
    FakeRecruitments,
    LoopingCatalog,
    OversizedCatalog,
    make_opportunity,
    make_recruitment,
    service,
)

from app.core.errors import ApiError
from app.features.community.domain import RecruitmentStatus
from app.features.opportunities.repository import OpportunityFile, TargetScope
from app.features.opportunities.schemas import (
    OpportunityKind,
    PublicationStatus,
    SourceKind,
    SubmissionMode,
)
from app.features.opportunity_matching.ports import AcademicContext, AcademicMembership
from app.features.opportunity_matching.service import (
    MAX_CANDIDATES,
    Interests,
    normalize_interests,
)
from app.schemas.common import ErrorCode

NONE = Interests()


def uid(n: int) -> UUID:
    return UUID(f"00000000-0000-4000-9000-{n:012d}")


def ids(page) -> list[UUID]:
    return [item.opportunity.id for item in page.items]


def run(catalog, user=USER_A, interests=NONE, *, svc=None, **kwargs):
    params = dict(kind=None, include_closed=False, limit=20, cursor=None) | kwargs
    return (svc or service(catalog)).list_matches(user, interests, **params)


def codes_of(item) -> list[str]:
    return [reason.code for reason in item.reasons]


SCHOOL = make_opportunity(id=uid(1), title="전교 장학")
CSE_DEPT = make_opportunity(
    id=uid(2), title="컴퓨터 학과 장학", target_scope=TargetScope("department", ("CSE",))
)
EE_DEPT = make_opportunity(
    id=uid(3), title="전자 학과 장학", target_scope=TargetScope("department", ("EE",))
)
CSE_Y2 = make_opportunity(
    id=uid(4), title="컴퓨터 2학년", target_scope=TargetScope("grade", ("CSE",), (2,))
)
ANY_Y3 = make_opportunity(
    id=uid(5), title="전 학과 3학년", target_scope=TargetScope("grade", (), (3,))
)


def test_scope_matching_uses_current_department_and_year():
    catalog = FakeCatalog([SCHOOL, CSE_DEPT, EE_DEPT, CSE_Y2, ANY_Y3])
    page_a = run(catalog, USER_A)
    page_b = run(catalog, USER_B)
    assert set(ids(page_a)) == {SCHOOL.id, CSE_DEPT.id, CSE_Y2.id}
    assert set(ids(page_b)) == {SCHOOL.id, EE_DEPT.id, ANY_Y3.id}
    by_id = {item.opportunity.id: item for item in page_a.items}
    assert codes_of(by_id[SCHOOL.id])[0] == "SCHOOL_WIDE"
    assert codes_of(by_id[CSE_Y2.id])[:2] == ["DEPARTMENT_MATCH", "GRADE_MATCH"]
    assert page_a.context.model_dump() == {
        "memberships": [{"department_code": "CSE", "grade": 2}],
        "interest_kinds": [],
        "interest_keywords": [],
    }


def test_grade_scope_requires_department_and_year_in_the_same_membership():
    contexts = FakeContexts(
        {
            USER_C: AcademicContext(
                USER_C, (AcademicMembership("CSE", 1), AcademicMembership("EE", 2))
            )
        }
    )
    cross = make_opportunity(id=uid(9), target_scope=TargetScope("grade", ("CSE",), (2,)))
    page = run(FakeCatalog([cross]), USER_C, svc=service(FakeCatalog([cross]), contexts))
    assert page.items == []


def test_missing_or_foreign_context_is_forbidden_and_invalid_memberships_are_dropped():
    catalog = FakeCatalog([SCHOOL])
    contexts = FakeContexts({USER_A: None, USER_B: AcademicContext(USER_A, ())})
    for user in (USER_A, USER_B, USER_C):
        with pytest.raises(ApiError) as exc:
            run(catalog, user, svc=service(catalog, contexts))
        assert exc.value.code is ErrorCode.FORBIDDEN
    contexts = FakeContexts(
        {
            USER_C: AcademicContext(
                USER_C,
                (
                    AcademicMembership("CSE", 9),
                    AcademicMembership("../x", 1),
                    AcademicMembership("EE", None),
                ),
            )
        }
    )
    page = run(catalog, USER_C, svc=service(catalog, contexts))
    assert [m.department_code for m in page.context.memberships] == ["EE"]
    assert contexts.calls == [USER_C]


def test_interest_reasons_and_bounded_scores():
    contest = make_opportunity(
        id=uid(10),
        kind=OpportunityKind.CONTEST,
        title="AI 해커톤 공모전",
        organization="가상 데이터 재단",
        eligibility="파이썬 경험",
        deadline_at=NOW + timedelta(days=30),
    )
    interests = normalize_interests([OpportunityKind.CONTEST], ["ai", "데이터", "파이썬", "해커톤"])
    (item,) = run(FakeCatalog([contest]), interests=interests).items
    assert [(r.code, r.source_field, r.value) for r in item.reasons] == [
        ("SCHOOL_WIDE", "target_scope.level", None),
        ("KIND_INTEREST", "kind", "contest"),
        ("KEYWORD_INTEREST", "title", "ai"),
        ("KEYWORD_INTEREST", "organization", "데이터"),
        ("KEYWORD_INTEREST", "eligibility", "파이썬"),
        ("KEYWORD_INTEREST", "title", "해커톤"),
    ]
    # school 10 + kind 15 + only two scored keywords (2*10).
    assert item.score == 45


def test_deadline_soon_reason_and_stable_sort():
    late = make_opportunity(id=uid(22), deadline_at=NOW + timedelta(days=20))
    soon = make_opportunity(id=uid(21), deadline_at=NOW + timedelta(days=2))
    tie_a = make_opportunity(id=uid(24), deadline_at=NOW + timedelta(days=20))
    no_deadline = make_opportunity(id=uid(23), deadline_at=None)
    page = run(FakeCatalog([no_deadline, tie_a, late, soon]))
    assert ids(page) == [soon.id, late.id, tie_a.id, no_deadline.id]
    assert "DEADLINE_SOON" in codes_of(page.items[0])
    assert page.items[-1].window == "NO_DEADLINE"
    again = run(FakeCatalog([soon, late, no_deadline, tie_a]))
    assert ids(again) == ids(page)


def test_window_closed_excluded_by_default_and_upcoming_marked():
    closed = make_opportunity(id=uid(30), deadline_at=NOW - timedelta(seconds=1))
    upcoming = make_opportunity(
        id=uid(31), apply_starts_at=NOW + timedelta(days=1), deadline_at=NOW + timedelta(days=9)
    )
    catalog = FakeCatalog([closed, upcoming])
    assert ids(run(catalog)) == [upcoming.id]
    assert run(catalog).items[0].window == "UPCOMING"
    windows = {i.opportunity.id: i.window for i in run(catalog, include_closed=True).items}
    assert windows == {closed.id: "CLOSED", upcoming.id: "UPCOMING"}


def test_freshness_and_safe_source_url():
    current = make_opportunity(
        id=uid(40),
        source_kind=SourceKind.OFFICIAL_PUBLIC,
        checked_at=NOW - timedelta(days=3),
        original_url="javascript:alert(1)",
        source_url="https://example.test/source",
    )
    stale = make_opportunity(id=uid(41), checked_at=NOW - timedelta(days=31))
    unverified = make_opportunity(id=uid(42), checked_at=None, original_url=None)
    items = {i.opportunity.id: i for i in run(FakeCatalog([current, stale, unverified])).items}
    assert items[current.id].freshness == "CURRENT"
    assert items[current.id].source_url == "https://example.test/source"
    assert items[stale.id].freshness == "STALE"
    assert items[unverified.id].freshness == "UNVERIFIED"
    assert items[unverified.id].source_url is None


def test_pagination_is_stable_and_cursor_bound_to_ranking_and_request():
    rows = [
        make_opportunity(id=uid(100 + n), deadline_at=NOW + timedelta(days=10 + n))
        for n in range(7)
    ]
    catalog = FakeCatalog(rows)
    seen: list[UUID] = []
    cursor = None
    while True:
        page = run(catalog, limit=3, cursor=cursor)
        seen += ids(page)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == [r.id for r in rows]

    first = run(catalog, limit=3)
    with pytest.raises(ApiError) as exc:
        run(catalog, limit=3, cursor=first.next_cursor, interests=normalize_interests([], ["x"]))
    assert exc.value.code is ErrorCode.CONFLICT
    catalog.records[uid(200)] = make_opportunity(id=uid(200), deadline_at=NOW + timedelta(days=1))
    with pytest.raises(ApiError) as exc:
        run(catalog, limit=3, cursor=first.next_cursor)
    assert exc.value.code is ErrorCode.CONFLICT
    for bad in ("abc", "0." + "0" * 16, "-1.0000000000000000", "99." + first.next_cursor[2:]):
        with pytest.raises(ApiError) as exc:
            run(catalog, limit=3, cursor=bad)
        assert exc.value.code in {ErrorCode.VALIDATION, ErrorCode.CONFLICT}
    with pytest.raises(ApiError) as exc:
        run(catalog, limit=21)
    assert exc.value.code is ErrorCode.VALIDATION


def test_candidate_cap_and_complete_flag():
    small = FakeCatalog([make_opportunity(id=uid(300 + n)) for n in range(60)])
    page = run(small)
    assert (page.candidates_scanned, page.complete, page.candidate_cap) == (
        60,
        True,
        MAX_CANDIDATES,
    )

    big = FakeCatalog([make_opportunity(id=uid(1000 + n)) for n in range(MAX_CANDIDATES + 10)])
    page = run(big)
    assert page.candidates_scanned == MAX_CANDIDATES
    assert page.complete is False

    exact = FakeCatalog([make_opportunity(id=uid(2000 + n)) for n in range(MAX_CANDIDATES)])
    assert run(exact).complete is True

    rows = [make_opportunity(id=uid(3000 + n)) for n in range(60)]
    looping = run(LoopingCatalog(rows))
    assert looping.complete is False and looping.candidates_scanned == 4
    oversized = run(OversizedCatalog(rows))
    assert oversized.complete is False and oversized.candidates_scanned == 50


def test_malformed_rows_are_omitted_without_metadata():
    malformed = [
        make_opportunity(id=uid(400), title="naive", deadline_at=datetime(2026, 11, 30)),
        make_opportunity(
            id=uid(401),
            title="역전된 기간",
            apply_starts_at=NOW + timedelta(days=5),
            deadline_at=NOW + timedelta(days=2),
        ),
        make_opportunity(
            id=uid(402), title="빈 학년", target_scope=TargetScope("grade", ("CSE",), ())
        ),
        make_opportunity(id=uid(403), title="모르는 범위", target_scope=TargetScope("campus")),
        make_opportunity(id=uid(404), title="미래 확인", checked_at=NOW + timedelta(days=1)),
        make_opportunity(id=uid(405), title="   "),
        make_opportunity(
            id=uid(406), title="학년 범위 밖", target_scope=TargetScope("grade", (), (9,))
        ),
        make_opportunity(
            id=uid(407), title="학교+학과", target_scope=TargetScope("school", ("CSE",))
        ),
    ]
    # The fake's own filter would trip on naive datetimes; pass rows through like a raw adapter.
    page = run(FakeCatalog([SCHOOL, *malformed], leak_unfiltered=True))
    assert ids(page) == [SCHOOL.id]
    assert page.omitted_count == len(malformed)
    dumped = page.model_dump_json()
    for row in malformed:
        assert str(row.id) not in dumped


def test_duplicate_and_unpublished_rows_from_adapter_are_dropped():
    draft = make_opportunity(id=uid(500), status=PublicationStatus.DRAFT, title="초안 비공개")
    catalog = FakeCatalog([SCHOOL, draft], leak_unfiltered=True)
    page = run(catalog)
    assert ids(page) == [SCHOOL.id]
    assert page.omitted_count == 0
    assert "초안 비공개" not in page.model_dump_json()
    dup = OversizedCatalog([SCHOOL, SCHOOL])
    assert run(dup).omitted_count == 1


def test_interest_validation():
    with pytest.raises(ApiError):
        normalize_interests([], ["a"] * 6)
    with pytest.raises(ApiError):
        normalize_interests([OpportunityKind.CONTEST] * 6, [])
    for bad in ("", "   ", "x" * 21, "탭\t문자"):
        with pytest.raises(ApiError):
            normalize_interests([], [bad])
    interests = normalize_interests(
        [OpportunityKind.CONTEST, OpportunityKind.CONTEST], [" AI ", "ai", "데이터"]
    )
    assert interests == Interests((OpportunityKind.CONTEST,), ("AI", "데이터"))


def test_recruitment_reference_seam_projects_only_public_fields():
    contest = make_opportunity(id=uid(600), kind=OpportunityKind.CONTEST)
    catalog = FakeCatalog([contest])
    assert run(catalog).items[0].recruitment.status == "NOT_CONNECTED"

    reader = FakeRecruitments(
        [
            make_recruitment(contest.id, id="rec-2", deadline_at=NOW + timedelta(days=5)),
            make_recruitment(contest.id, id="rec-1", field="데이터 분석"),
            make_recruitment(contest.id, id="rec-closed", status=RecruitmentStatus.CLOSED),
            make_recruitment(contest.id, id="rec-expired", deadline_at=NOW - timedelta(hours=1)),
            make_recruitment(contest.id, id="rec-naive", deadline_at=datetime(2026, 12, 1)),
            make_recruitment(uid(999), id="rec-other"),
        ]
    )
    svc = service(catalog, recruitments=reader)
    page = run(catalog, interests=normalize_interests([], ["데이터"]), svc=svc)
    refs = page.items[0].recruitment
    assert refs.status == "AVAILABLE" and refs.open_count == 2
    assert [r.id for r in refs.items] == ["rec-1", "rec-2"]
    assert refs.items[0].matched_keywords == ["데이터"]
    assert refs.items[1].matched_keywords == []
    dumped = page.model_dump_json()
    assert OWNER_SECRET not in dumped and BODY_SECRET not in dumped
    assert "owner_id" not in dumped and "accepted_count" not in dumped
    assert reader.calls == [[contest.id]]

    failing = service(catalog, recruitments=FakeRecruitments(fail=True))
    page = run(catalog, svc=failing)
    assert page.items[0].recruitment.status == "UNAVAILABLE"
    assert "adapter detail" not in page.model_dump_json()


def test_provenance_never_claims_ai_or_eligibility():
    page = run(FakeCatalog([SCHOOL]))
    assert page.provenance.model_dump() | {"notice": None} == {
        "generator": "deterministic_rules_v1",
        "ai_generated": False,
        "eligibility_guaranteed": False,
        "notice": None,
    }
    assert "AI가 생성하지 않았" in page.provenance.notice
    assert page.evaluated_at == NOW


# ---- FR-AI-002 brief ----


def brief(record, user=USER_A, interests=NONE, **kwargs):
    return service(FakeCatalog([record]), **kwargs).brief(user, record.id, interests)


def steps(result):
    return [
        (s.code, s.available, s.evidence_field, s.evidence_value, s.evidence_url)
        for s in result.procedure
    ]


def test_brief_document_submission_procedure_uses_original_fields():
    record = make_opportunity(
        id=uid(700),
        eligibility="원문 자격 문구 그대로",
        destination=None,
        original_url="https://example.test/notice",
        files=(
            OpportunityFile("form.hwp", "https://example.test/form.hwp"),
            OpportunityFile("bad.hwp", "javascript:alert(1)"),
        ),
    )
    result = brief(record)
    assert result.opportunity.eligibility == "원문 자격 문구 그대로"
    assert steps(result) == [
        ("CHECK_ORIGINAL", True, "original_url", None, "https://example.test/notice"),
        ("DOWNLOAD_FORM", True, "files", "form.hwp", "https://example.test/form.hwp"),
        ("DOWNLOAD_FORM", False, "files", "bad.hwp", None),
        ("SUBMIT_TO_DESTINATION", False, "destination", None, None),
        ("SELF_RECORD", True, "submission_mode", "external_document_submission", None),
    ]
    assert [s.order for s in result.procedure] == [1, 2, 3, 4, 5]
    cautions = [c.code for c in result.cautions]
    assert cautions[:2] == ["NOT_ELIGIBILITY_DECISION", "EXTERNAL_SUBMISSION"]
    assert {"DEMO_SOURCE", "NEEDS_VERIFICATION", "UNVERIFIED_SOURCE"} <= set(cautions)
    assert result.opportunity.platform_receives_submission is False
    assert result.provenance.ai_generated is False


def test_brief_link_info_only_and_missing_files():
    link = make_opportunity(id=uid(701), submission_mode=SubmissionMode.EXTERNAL_LINK, files=())
    assert [s[0] for s in steps(brief(link))] == ["CHECK_ORIGINAL", "APPLY_VIA_LINK", "SELF_RECORD"]
    info = make_opportunity(
        id=uid(702), submission_mode=SubmissionMode.INFO_ONLY, original_url=None, files=()
    )
    result = brief(info)
    assert steps(result) == [("CHECK_ORIGINAL", False, "original_url", None, None)]
    assert "NO_APPLICATION_PROCEDURE" in [c.code for c in result.cautions]
    doc = make_opportunity(id=uid(703), files=())
    assert ("DOWNLOAD_FORM", False, "files", None, None) in steps(brief(doc))


def test_brief_out_of_scope_and_window_cautions():
    record = make_opportunity(
        id=uid(704),
        target_scope=TargetScope("department", ("EE",)),
        deadline_at=NOW - timedelta(days=1),
    )
    result = brief(record, interests=normalize_interests([OpportunityKind.SCHOLARSHIP], []))
    assert result.match.in_scope is False
    assert [r.code for r in result.match.reasons] == ["KIND_INTEREST"]
    assert {"OUT_OF_SCOPE", "DEADLINE_PASSED"} <= {c.code for c in result.cautions}
    assert result.window == "CLOSED"
    assert brief(record, USER_B).match.in_scope is True


def test_brief_hides_missing_draft_and_malformed_rows_identically():
    draft = make_opportunity(id=uid(800), status=PublicationStatus.DRAFT)
    naive = make_opportunity(id=uid(801), deadline_at=datetime(2026, 11, 30))
    for record in (draft, naive):
        with pytest.raises(ApiError) as exc:
            brief(record)
        assert exc.value.code is ErrorCode.NOT_FOUND
    with pytest.raises(ApiError) as exc:
        service(FakeCatalog([])).brief(USER_A, uid(802), NONE)
    assert exc.value.code is ErrorCode.NOT_FOUND
    with pytest.raises(ApiError) as exc:
        service(FakeCatalog([SCHOOL]), FakeContexts({})).brief(USER_A, SCHOOL.id, NONE)
    assert exc.value.code is ErrorCode.FORBIDDEN
