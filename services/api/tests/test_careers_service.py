"""API-JOB service rules against test-only fakes (TC-V1-JOB-001~004, TC-V1-OPP-005~006)."""

import threading
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_careers_support import (
    ALL_STUDENT,
    NOW,
    USER_A,
    USER_B,
    FakeUnitOfWork,
    InjectedFailure,
    actor,
    bump_revision,
    demo_policy,
    make_program,
)
from test_opportunities_support import FakeCatalog, make_opportunity

from app.core.errors import ApiError
from app.features.careers import CareerGrant, ContestTeamLinkVisibility, DemoCareerPolicy
from app.features.careers.domain import (
    Provenance,
    reject_contact_details,
    safe_external_url,
)
from app.features.careers.schemas import (
    ApplicationCreate,
    EmployerDraftCreate,
    EmployerDraftPatch,
    ProfileCreate,
    ProfilePatch,
)
from app.features.careers.service import CareersService
from app.features.community.repository import OpportunityVisibility
from app.features.opportunities.schemas import OpportunityKind, PublicationStatus, SourceKind
from app.schemas.common import ErrorCode


def code(excinfo) -> ErrorCode:
    return excinfo.value.code


def service(uow=None, catalog=None, policy=None, clock=lambda: NOW) -> CareersService:
    return CareersService(policy or demo_policy(), catalog=catalog, uow=uow, clock=clock)


def job(**overrides):
    values = dict(
        kind=OpportunityKind.CAREER,
        title="[DEMO] 가상 백엔드 인턴",
        organization="가상 기업",
        source_kind=SourceKind.DEMO,
    )
    values.update(overrides)
    return make_opportunity(**values)


@pytest.fixture
def uow():
    store = FakeUnitOfWork()
    store.grant(USER_A, *ALL_STUDENT)
    store.grant(USER_B, *ALL_STUDENT)
    return store


# ------------------------------------------------------------------ policy separation


def test_demo_policy_has_no_default_and_must_be_labelled_demo():
    with pytest.raises(TypeError):
        DemoCareerPolicy()  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        demo_policy(basis="SCHOOL")
    with pytest.raises(ValueError):
        demo_policy(max_active_applications_per_user=0)
    with pytest.raises(ValueError):
        demo_policy(policy_id="Bad Policy")


def test_unconfigured_ports_fail_closed():
    svc = service()
    with pytest.raises(ApiError) as missing_catalog:
        svc.list_jobs()
    with pytest.raises(ApiError) as missing_uow:
        svc.get_profile(actor())
    assert code(missing_catalog) is code(missing_uow) is ErrorCode.UNAVAILABLE


# ------------------------------------------------------------------ FR-JOB-001 jobs


def test_jobs_reuse_catalog_and_only_return_published_careers():
    career, scholarship = job(), make_opportunity()
    draft = job(status=PublicationStatus.DRAFT)
    svc = service(catalog=FakeCatalog([career, scholarship, draft], leak_unfiltered=True))
    page = svc.list_jobs()
    assert [item.id for item in page.items] == [career.id]
    assert page.items[0].platform_receives_application is False
    for hidden in (scholarship.id, draft.id, uuid4()):
        with pytest.raises(ApiError) as excinfo:
            svc.get_job(hidden)
        assert code(excinfo) is ErrorCode.NOT_FOUND


def test_provenance_official_requires_safe_url_and_checked_date():
    checked = datetime(2026, 10, 29, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    official = job(
        source_kind=SourceKind.OFFICIAL_PUBLIC,
        original_url="https://job.dit.ac.kr/page/main/",
        checked_at=checked,
    )
    no_date = job(source_kind=SourceKind.OFFICIAL_PUBLIC, original_url="https://job.dit.ac.kr/")
    bad_url = job(
        source_kind=SourceKind.OFFICIAL_PUBLIC,
        original_url="javascript:alert(1)",
        checked_at=checked,
    )
    demo = job()
    svc = service(catalog=FakeCatalog([official, no_date, bad_url, demo]))
    by_id = {item.id: item for item in svc.list_jobs().items}
    assert by_id[official.id].provenance is Provenance.OFFICIAL_PUBLIC
    assert by_id[official.id].checked_at.utcoffset() == timedelta(0)  # normalised to UTC
    assert by_id[no_date.id].provenance is Provenance.UNKNOWN
    assert by_id[bad_url.id].provenance is Provenance.UNKNOWN
    assert by_id[bad_url.id].original_url is None
    assert by_id[demo.id].provenance is Provenance.DEMO


def test_naive_datetimes_from_adapter_are_dropped_not_guessed():
    naive = job(deadline_at=datetime(2026, 11, 1, 0, 0))
    svc = service(catalog=FakeCatalog([naive], leak_unfiltered=True), clock=lambda: NOW)
    assert svc.list_jobs().items == []


def test_open_only_search_drops_naive_row_instead_of_failing_the_page():
    # L1: open_only compares deadlines, so the naive row must be dropped before that compare.
    naive = job(deadline_at=datetime(2026, 11, 1, 0, 0))
    good = job(deadline_at=NOW + timedelta(days=3))
    closed = job(deadline_at=NOW - timedelta(days=1))
    svc = service(catalog=FakeCatalog([naive, good, closed], leak_unfiltered=True))
    assert [item.id for item in svc.list_jobs(open_only=True).items] == [good.id]
    assert {item.id for item in svc.list_jobs(open_only=False).items} == {good.id, closed.id}
    naive_contest = make_opportunity(
        kind=OpportunityKind.CONTEST, deadline_at=datetime(2026, 11, 1, 0, 0)
    )
    contests = service(catalog=FakeCatalog([naive_contest], leak_unfiltered=True))
    assert contests.list_contests().items == []


@pytest.mark.parametrize(
    "url",
    [
        "http://job.dit.ac.kr/",
        "https://user:pw@job.dit.ac.kr/",
        "https://job.dit.ac.kr:8443/",
        "https://job.dit.ac.kr/‮x",
        "data:text/html,x",
        "//job.dit.ac.kr/",
        "https:///nohost",
    ],
)
def test_unsafe_external_urls_are_removed(url):
    assert safe_external_url(url) is None


def test_job_query_limit_is_bounded():
    with pytest.raises(ApiError) as excinfo:
        service(catalog=FakeCatalog([])).list_jobs(limit=51)
    assert code(excinfo) is ErrorCode.VALIDATION


# ------------------------------------------------------------------ FR-OPP-005 contest link seam


def test_contest_candidates_and_community_seam_agree():
    open_contest = make_opportunity(kind=OpportunityKind.CONTEST, title="[DEMO] 가상 공모전")
    closed = make_opportunity(kind=OpportunityKind.CONTEST, deadline_at=NOW - timedelta(days=1))
    hidden = make_opportunity(kind=OpportunityKind.CONTEST, status=PublicationStatus.DRAFT)
    scholarship = make_opportunity()
    catalog = FakeCatalog([open_contest, closed, hidden, scholarship])
    page = service(catalog=catalog).list_contests()
    flags = {item.opportunity_id: item.team_link_candidate for item in page.items}
    assert flags == {open_contest.id: True, closed.id: False}

    seam: OpportunityVisibility = ContestTeamLinkVisibility(
        catalog, demo_policy(), clock=lambda: NOW
    )
    assert seam.is_linkable(str(USER_A), str(open_contest.id)) is True
    for target in (closed.id, hidden.id, scholarship.id, uuid4()):
        assert seam.is_linkable(str(USER_A), str(target)) is False
    assert seam.is_linkable(str(USER_A), "not-a-uuid") is False

    lenient = ContestTeamLinkVisibility(
        catalog, demo_policy(link_closed_contests=True), clock=lambda: NOW
    )
    assert lenient.is_linkable(str(USER_A), str(closed.id)) is True
    assert lenient.is_linkable(str(USER_A), str(hidden.id)) is False


@pytest.mark.parametrize("closed_ok", [False, True])
def test_contest_link_refuses_naive_deadline_or_clock(closed_ok):
    # L2: a malformed time is refused (False), never a TypeError/500, even if closed is allowed.
    naive = make_opportunity(kind=OpportunityKind.CONTEST, deadline_at=datetime(2026, 11, 1))
    aware = make_opportunity(kind=OpportunityKind.CONTEST, deadline_at=NOW + timedelta(days=1))
    no_deadline = make_opportunity(kind=OpportunityKind.CONTEST, deadline_at=None)
    catalog = FakeCatalog([naive, aware, no_deadline])
    policy = demo_policy(link_closed_contests=closed_ok)
    seam = ContestTeamLinkVisibility(catalog, policy, clock=lambda: NOW)
    assert seam.is_linkable(str(USER_A), str(naive.id)) is False
    assert seam.is_linkable(str(USER_A), str(aware.id)) is True
    assert seam.is_linkable(str(USER_A), str(no_deadline.id)) is True

    naive_clock = ContestTeamLinkVisibility(catalog, policy, clock=lambda: datetime(2026, 10, 30))
    for target in (naive, aware, no_deadline):
        assert naive_clock.is_linkable(str(USER_A), str(target.id)) is False
    kst = timezone(timedelta(hours=9))
    # Same instant in another zone: compared as UTC, so 1 second before the deadline is open.
    before = ContestTeamLinkVisibility(
        catalog,
        demo_policy(),
        clock=lambda: (aware.deadline_at - timedelta(seconds=1)).astimezone(kst),
    )
    at = ContestTeamLinkVisibility(
        catalog, demo_policy(), clock=lambda: aware.deadline_at.astimezone(kst)
    )
    assert before.is_linkable(str(USER_A), str(aware.id)) is True
    assert at.is_linkable(str(USER_A), str(aware.id)) is False


# ------------------------------------------------------------------ FR-JOB-002 virtual profile


def profile_body(**overrides) -> ProfileCreate:
    values = dict(alias="별빛개발자", desired_roles=["백엔드"], skills=["Python", "SQL"])
    values.update(overrides)
    return ProfileCreate(**values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("alias", "me@example.com"),
        ("alias", "010-1234-5678"),
        ("summary", "포트폴리오 https://example.com"),
        ("summary", "주민번호 900101-1234567"),
        ("skills", ["www.github.io"]),
        ("skills", ["blog.example.kr"]),
        ("alias", "a​b"),
        ("alias", "두줄\n별칭"),
    ],
)
def test_profile_rejects_contacts_links_ids_and_controls(field, value):
    with pytest.raises(ValidationError):
        profile_body(**{field: value})


@pytest.mark.parametrize("extra", ["user_id", "name", "phone", "email", "resume_file"])
def test_profile_rejects_identity_and_file_fields(extra):
    with pytest.raises(ValidationError):
        ProfileCreate(alias="별빛개발자", **{extra: "x"})


def test_profile_is_owner_scoped_and_create_is_idempotent(uow):
    svc = service(uow)
    created, replayed = svc.create_profile(actor(USER_A), profile_body(), "key-profile-1")
    assert replayed is False and created.is_virtual is True and created.shared_with == []
    again, replayed = svc.create_profile(actor(USER_A), profile_body(), "key-profile-1")
    assert replayed is True and again.id == created.id
    assert len(uow.profiles) == 1
    assert svc.get_profile(actor(USER_B)).profile is None  # other user sees nothing

    with pytest.raises(ApiError) as changed_body:
        svc.create_profile(actor(USER_A), profile_body(alias="다른별칭"), "key-profile-1")
    with pytest.raises(ApiError) as second_profile:
        svc.create_profile(actor(USER_A), profile_body(), "key-profile-2")
    assert code(changed_body) is code(second_profile) is ErrorCode.CONFLICT

    # Same key from another actor is a different scope, not a replay of A's profile.
    other, replayed = svc.create_profile(actor(USER_B), profile_body(), "key-profile-1")
    assert replayed is False and other.id != created.id


def test_profile_update_uses_revision_cas(uow):
    svc = service(uow)
    created, _ = svc.create_profile(actor(), profile_body(), "key-profile-1")
    updated = svc.update_profile(actor(), ProfilePatch(skills=["Go"]), created.revision)
    assert updated.revision == 2 and updated.skills == ["Go"]
    with pytest.raises(ApiError) as stale:
        svc.update_profile(actor(), ProfilePatch(summary="x"), created.revision)
    assert code(stale) is ErrorCode.CONFLICT
    with pytest.raises(ApiError) as other:
        svc.update_profile(actor(USER_B), ProfilePatch(summary="x"), 2)
    assert code(other) is ErrorCode.NOT_FOUND

    # Concurrent writer between our read and CAS: the store refuses and nothing changes.
    class RacingUow:
        def transaction(self):
            ctx = uow.transaction()
            tx = ctx.__enter__()
            original = tx.update_profile

            def racing(record, expected):
                bump_revision(uow, record.id)
                return original(record, expected)

            tx.update_profile = racing

            class Wrapper:
                def __enter__(self):
                    return tx

                def __exit__(self, *exc):
                    return ctx.__exit__(*exc)

            return Wrapper()

    with pytest.raises(ApiError) as raced:
        service(RacingUow()).update_profile(actor(), ProfilePatch(summary="경합"), 2)
    assert code(raced) is ErrorCode.CONFLICT
    assert uow.profiles[created.id].summary == ""  # rolled back with the snapshot


def test_profile_delete_keeps_tombstone_and_late_retry_cannot_resurrect(uow):
    svc = service(uow)
    created, _ = svc.create_profile(actor(), profile_body(), "key-profile-1")
    with pytest.raises(ApiError) as stale:
        svc.delete_profile(actor(), 99)
    assert code(stale) is ErrorCode.CONFLICT
    svc.delete_profile(actor(), created.revision)
    assert uow.profiles == {} and len(uow.claims) == 1  # claim retained as tombstone
    with pytest.raises(ApiError) as late:
        svc.create_profile(actor(), profile_body(), "key-profile-1")
    assert code(late) is ErrorCode.CONFLICT and uow.profiles == {}
    fresh, replayed = svc.create_profile(actor(), profile_body(), "key-profile-new")
    assert replayed is False and fresh.id != created.id


def test_grant_is_rechecked_on_replay_after_revocation(uow):
    svc = service(uow)
    svc.create_profile(actor(), profile_body(), "key-profile-1")
    uow.grant(USER_A)  # revoke everything
    for call in (
        lambda: svc.create_profile(actor(), profile_body(), "key-profile-1"),
        lambda: svc.get_profile(actor()),
        lambda: svc.delete_profile(actor(), 1),
    ):
        with pytest.raises(ApiError) as excinfo:
            call()
        assert code(excinfo) is ErrorCode.FORBIDDEN


def test_unauthenticated_never_opens_a_transaction(uow):
    with pytest.raises(ApiError) as excinfo:
        service(uow).get_profile(None)
    assert code(excinfo) is ErrorCode.UNAUTHORIZED and uow.transactions == 0


def test_failure_inside_transaction_rolls_back_resource_and_claim(uow):
    uow.fail_put_claim = True
    with pytest.raises(InjectedFailure):
        service(uow).create_profile(actor(), profile_body(), "key-profile-1")
    assert uow.profiles == {} and uow.claims == {}


def test_same_key_concurrent_creates_store_one_profile(uow):
    svc = service(uow)
    results, errors = [], []

    def run():
        try:
            results.append(svc.create_profile(actor(), profile_body(), "key-profile-race"))
        except ApiError as exc:
            errors.append(exc.code)

    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and len(uow.profiles) == 1
    assert {r[0].id for r in results} == set(uow.profiles)
    assert sorted(r[1] for r in results) == [False] + [True] * 7


# ------------------------------------------------------------------ FR-JOB-003 / FR-OPP-006


def test_virtual_application_happy_path_and_owner_scope(uow):
    program = make_program()
    uow.programs[program.id] = program
    svc = service(uow)
    listing = svc.list_programs()
    assert listing.policy_basis == "DEMO" and listing.items[0].accepts_virtual_application
    app, replayed = svc.apply(actor(), program.id, ApplicationCreate(note="참여 희망"), "key-app-1")
    assert replayed is False and app.review_status == "not_reviewed" and app.is_virtual
    assert [a.id for a in svc.list_applications(actor()).items] == [app.id]
    assert svc.list_applications(actor(USER_B)).items == []
    for call in (
        lambda: svc.get_application(actor(USER_B), app.id),
        lambda: svc.cancel_application(actor(USER_B), app.id, 1),
    ):
        with pytest.raises(ApiError) as excinfo:
            call()
        assert code(excinfo) is ErrorCode.NOT_FOUND


@pytest.mark.parametrize(
    "overrides",
    [
        dict(official=True, source_url="https://job.dit.ac.kr/", checked_at=NOW),
        dict(official=True),  # UNKNOWN provenance is still not a demo program
        dict(apply_ends_at=NOW - timedelta(minutes=1)),
        dict(apply_starts_at=NOW + timedelta(days=1)),
    ],
)
def test_official_or_closed_programs_reject_virtual_application(uow, overrides):
    program = make_program(**overrides)
    uow.programs[program.id] = program
    with pytest.raises(ApiError) as excinfo:
        service(uow).apply(actor(), program.id, ApplicationCreate(), "key-app-1")
    assert code(excinfo) is ErrorCode.CONFLICT and uow.applications == {}


def test_window_rule_comes_only_from_injected_policy(uow):
    program = make_program(apply_ends_at=NOW - timedelta(minutes=1))
    uow.programs[program.id] = program
    lenient = service(uow, policy=demo_policy(enforce_program_window=False))
    app, _ = lenient.apply(actor(), program.id, ApplicationCreate(), "key-app-1")
    assert app.program is not None and app.program.window_open is False


def test_hidden_or_missing_program_is_404_after_grant_check(uow):
    hidden = make_program(published=False)
    uow.programs[hidden.id] = hidden
    svc = service(uow)
    for target in (hidden.id, uuid4()):
        with pytest.raises(ApiError) as excinfo:
            svc.apply(actor(), target, ApplicationCreate(), "key-app-1")
        assert code(excinfo) is ErrorCode.NOT_FOUND
    uow.grant(USER_A)
    with pytest.raises(ApiError) as forbidden:
        svc.apply(actor(), hidden.id, ApplicationCreate(), "key-app-1")
    assert code(forbidden) is ErrorCode.FORBIDDEN


def test_duplicate_capacity_and_per_user_limits(uow):
    first, second, third = make_program(capacity=1), make_program(), make_program()
    for p in (first, second, third):
        uow.programs[p.id] = p
    svc = service(uow, policy=demo_policy(max_active_applications_per_user=2))
    svc.apply(actor(USER_A), first.id, ApplicationCreate(), "key-app-1")
    for user, program, key in (
        (USER_A, first.id, "key-app-dup"),  # duplicate active application
        (USER_B, first.id, "key-app-cap"),  # capacity 1 reached
    ):
        with pytest.raises(ApiError) as excinfo:
            svc.apply(actor(user), program, ApplicationCreate(), key)
        assert code(excinfo) is ErrorCode.CONFLICT
    svc.apply(actor(USER_A), second.id, ApplicationCreate(), "key-app-2")
    with pytest.raises(ApiError) as limit:
        svc.apply(actor(USER_A), third.id, ApplicationCreate(), "key-app-3")
    assert code(limit) is ErrorCode.CONFLICT


def test_concurrent_applications_never_exceed_capacity(uow):
    program = make_program(capacity=1)
    uow.programs[program.id] = program
    users = [uuid4() for _ in range(10)]
    for user in users:
        uow.grant(user, CareerGrant.PROGRAM_APPLY_SELF)
    svc = service(uow)
    outcomes = []

    def run(user):
        try:
            svc.apply(actor(user), program.id, ApplicationCreate(), "key-app-race")
            outcomes.append("ok")
        except ApiError as exc:
            outcomes.append(exc.code)

    threads = [threading.Thread(target=run, args=(u,)) for u in users]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert outcomes.count("ok") == 1 and outcomes.count(ErrorCode.CONFLICT) == 9
    assert len(uow.applications) == 1


def test_cancel_cas_policy_and_replay_shows_current_state(uow):
    program = make_program()
    uow.programs[program.id] = program
    svc = service(uow)
    app, _ = svc.apply(actor(), program.id, ApplicationCreate(), "key-app-1")
    with pytest.raises(ApiError) as stale:
        svc.cancel_application(actor(), app.id, 5)
    assert code(stale) is ErrorCode.CONFLICT
    cancelled = svc.cancel_application(actor(), app.id, app.revision)
    assert cancelled.status == "cancelled" and cancelled.cancelled_at is not None
    replay, replayed = svc.apply(actor(), program.id, ApplicationCreate(), "key-app-1")
    assert replayed is True and replay.status == "cancelled"  # no stale "applied" success
    with pytest.raises(ApiError) as twice:
        svc.cancel_application(actor(), app.id, cancelled.revision)
    assert code(twice) is ErrorCode.CONFLICT


def test_cancel_after_window_follows_policy(uow):
    program = make_program()
    uow.programs[program.id] = program
    app, _ = service(uow).apply(actor(), program.id, ApplicationCreate(), "key-app-1")
    later = lambda: NOW + timedelta(days=30)  # noqa: E731
    with pytest.raises(ApiError) as blocked:
        service(uow, clock=later).cancel_application(actor(), app.id, 1)
    assert code(blocked) is ErrorCode.CONFLICT
    allowed = service(uow, clock=later, policy=demo_policy(allow_cancel_after_window=True))
    assert allowed.cancel_application(actor(), app.id, 1).status == "cancelled"


# ------------------------------------------------------------------ FR-JOB-004 employer drafts


def draft_body(**overrides) -> EmployerDraftCreate:
    values = dict(
        company_alias="가상테크",
        role_title="[DEMO] 백엔드 인턴",
        description="가상 시연용 채용의뢰 초안",
        employment_type="internship",
        closes_at=NOW + timedelta(days=14),
    )
    values.update(overrides)
    return EmployerDraftCreate(**values)


def test_employer_drafts_need_server_grant_and_are_owner_scoped(uow):
    svc = service(uow)
    with pytest.raises(ApiError) as student:
        svc.create_employer_draft(actor(USER_A), draft_body(), "key-draft-1")
    assert code(student) is ErrorCode.FORBIDDEN and uow.drafts == {}

    drafter, other = uuid4(), uuid4()
    uow.grant(drafter, CareerGrant.EMPLOYER_DRAFT)
    uow.grant(other, CareerGrant.EMPLOYER_DRAFT)
    draft, _ = svc.create_employer_draft(actor(drafter), draft_body(), "key-draft-1")
    assert draft.status == "draft" and draft.publishable is False
    assert svc.list_employer_drafts(actor(other)).items == []
    for call in (
        lambda: svc.get_employer_draft(actor(other), draft.id),
        lambda: svc.update_employer_draft(actor(other), draft.id, EmployerDraftPatch(), 1),
        lambda: svc.delete_employer_draft(actor(other), draft.id, 1),
    ):
        with pytest.raises(ApiError) as excinfo:
            call()
        assert code(excinfo) is ErrorCode.NOT_FOUND


def test_employer_draft_dates_cas_limit_and_tombstone(uow):
    drafter = uuid4()
    uow.grant(drafter, CareerGrant.EMPLOYER_DRAFT)
    svc = service(uow, policy=demo_policy(max_employer_drafts_per_actor=1))
    with pytest.raises(ApiError) as past:
        svc.create_employer_draft(
            actor(drafter), draft_body(closes_at=NOW - timedelta(hours=1)), "key-draft-0"
        )
    assert code(past) is ErrorCode.VALIDATION
    with pytest.raises(ValidationError):
        draft_body(closes_at=datetime(2026, 12, 1))  # naive datetime refused by schema

    kst = timezone(timedelta(hours=9))
    draft, _ = svc.create_employer_draft(
        actor(drafter), draft_body(closes_at=datetime(2026, 11, 20, 18, tzinfo=kst)), "key-draft-1"
    )
    assert draft.closes_at == datetime(2026, 11, 20, 9, tzinfo=UTC)
    with pytest.raises(ApiError) as limit:
        svc.create_employer_draft(actor(drafter), draft_body(), "key-draft-2")
    assert code(limit) is ErrorCode.CONFLICT

    updated = svc.update_employer_draft(
        actor(drafter), draft.id, EmployerDraftPatch(role_title="[DEMO] 데이터 인턴"), 1
    )
    assert updated.revision == 2
    with pytest.raises(ApiError) as stale:
        svc.delete_employer_draft(actor(drafter), draft.id, 1)
    assert code(stale) is ErrorCode.CONFLICT
    svc.delete_employer_draft(actor(drafter), draft.id, 2)
    with pytest.raises(ApiError) as late:
        svc.create_employer_draft(
            actor(drafter),
            draft_body(closes_at=datetime(2026, 11, 20, 18, tzinfo=kst)),
            "key-draft-1",
        )
    assert code(late) is ErrorCode.CONFLICT and uow.drafts == {}


def test_contact_screen_accepts_plain_skill_text():
    assert reject_contact_details("Python 3년, React 2년") == "Python 3년, React 2년"


@pytest.mark.parametrize(
    "value",
    [
        "ASP.NET",
        "ASP.NET Core, ADO.NET, VB.NET",
        "asp.net.",
        "2023.03-2024.02 인턴",
        "2023.03 - 2024.02. 백엔드 인턴",
        "2023.03.01-2024.02.28 (현장실습)",
        "2024-01 ~ 2024-06 프로젝트",
    ],
)
def test_contact_screen_allows_technology_names_and_periods(value):
    # L3: technology names and year.month periods are not contacts.
    assert reject_contact_details(value) == value
    assert ProfileCreate(alias="별빛개발자", skills=["ASP.NET"], summary="2023.03-2024.02 인턴")


@pytest.mark.parametrize(
    "value",
    [
        "010-1234-5678",
        "010 1234 5678",
        "900101-1234567",
        "2023.03-2024.02 010-1234-5678",
        "2010-12-1234-5678",
        "2024.13-2025.01",
        "myname.net",
        "asp.net.kr",
        "x.asp.net",
        "foo-asp.net",
        "https://asp.net",
        "www.example.org",
        "me@example.com",
    ],
)
def test_contact_screen_still_blocks_real_contact_shapes(value):
    # Pattern screening only: it narrows obvious contacts, it does not prove none remain.
    with pytest.raises(ValueError):
        reject_contact_details(value)
    with pytest.raises(ValidationError):
        ProfileCreate(alias="별빛개발자", skills=[value])
