"""Unit tests for pure API-OPP rules (FR-OPP-001/003/004, TC-V1-OPP-001/003/004, TC-V1-X03)."""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_opportunities_support import (
    DEPARTMENT_SCOPE,
    NOW,
    USER_A,
    USER_B,
    FakeCatalog,
    FakeStore,
    make_opportunity,
)

from app.core.errors import ApiError
from app.features.opportunities.repository import OpportunityFile, OpportunityQuery
from app.features.opportunities.schemas import (
    CheckItemCreate,
    CheckItemPatch,
    OpportunityKind,
    PreparationStatus,
    PublicationStatus,
    SavedOpportunityPatch,
    SaveOpportunityRequest,
    SourceKind,
    SubmissionMode,
)
from app.features.opportunities.service import ALLOWED_TRANSITIONS, OpportunityService, safe_url
from app.schemas.common import ErrorCode

S = PreparationStatus


def code_of(exc_info) -> ErrorCode:
    return exc_info.value.code


@pytest.fixture
def world():
    scholarship = make_opportunity()
    contest = make_opportunity(
        kind=OpportunityKind.CONTEST, title="가상 공모전", target_scope=DEPARTMENT_SCOPE
    )
    info = make_opportunity(kind=OpportunityKind.EVENT, submission_mode=SubmissionMode.INFO_ONLY)
    expired = make_opportunity(title="마감된 가상 장학", deadline_at=NOW - timedelta(hours=1))
    draft = make_opportunity(title="비공개 초안", status=PublicationStatus.DRAFT)
    catalog = FakeCatalog([scholarship, contest, info, expired, draft])
    store = FakeStore()
    service = OpportunityService(catalog, store, clock=lambda: NOW)
    return dict(
        service=service,
        store=store,
        catalog=catalog,
        scholarship=scholarship,
        contest=contest,
        info=info,
        expired=expired,
        draft=draft,
    )


# ---- public catalog ----


def test_list_hides_unpublished_and_filters(world):
    service = world["service"]
    ids = {i.id for i in service.list_public(OpportunityQuery()).items}
    assert world["draft"].id not in ids
    assert len(ids) == 4
    contests = service.list_public(OpportunityQuery(kind=OpportunityKind.CONTEST)).items
    assert [c.id for c in contests] == [world["contest"].id]
    open_items = service.list_public(OpportunityQuery(open_only=True)).items
    assert world["expired"].id not in {i.id for i in open_items}
    other_department = service.list_public(OpportunityQuery(department_code="ETC")).items
    assert world["contest"].id not in {i.id for i in other_department}
    assert world["scholarship"].id in {i.id for i in other_department}
    assert [i.id for i in service.list_public(OpportunityQuery(text="공모전")).items] == [
        world["contest"].id
    ]


def test_list_drops_items_a_faulty_adapter_leaks(world):
    leaky = FakeCatalog(list(world["catalog"].records.values()), leak_unfiltered=True)
    items = OpportunityService(leaky, clock=lambda: NOW).list_public(OpportunityQuery()).items
    assert world["draft"].id not in {i.id for i in items}


def test_list_paginates_with_cursor(world):
    service = world["service"]
    first = service.list_public(OpportunityQuery(limit=2))
    assert len(first.items) == 2 and first.next_cursor
    second = service.list_public(OpportunityQuery(limit=2, cursor=first.next_cursor))
    assert {i.id for i in first.items}.isdisjoint({i.id for i in second.items})


@pytest.mark.parametrize("limit", [0, 51])
def test_list_limit_bounds(world, limit):
    with pytest.raises(ApiError) as exc:
        world["service"].list_public(OpportunityQuery(limit=limit))
    assert code_of(exc) == ErrorCode.VALIDATION


def test_detail_guidance_and_demo_flag(world):
    detail = world["service"].get_public(world["scholarship"].id)
    assert detail.submission_mode is SubmissionMode.EXTERNAL_DOCUMENT_SUBMISSION
    assert detail.platform_receives_submission is False
    assert detail.source_kind is SourceKind.DEMO and detail.needs_verification
    assert detail.files[0].original_url == "https://example.test/demo-form.hwp"
    assert detail.deadline_passed is False
    assert world["service"].get_public(world["expired"].id).deadline_passed is True


def test_detail_hidden_for_draft_and_missing(world):
    for opportunity_id in (world["draft"].id, uuid4()):
        with pytest.raises(ApiError) as exc:
            world["service"].get_public(opportunity_id)
        assert code_of(exc) == ErrorCode.NOT_FOUND


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "data:text/html,x", "/relative", "https://u:p@x.test", "ftp://x.test"],
)
def test_unsafe_urls_are_dropped(url):
    assert safe_url(url) is None


def test_detail_never_returns_unsafe_links(world):
    record = make_opportunity(
        source_kind=SourceKind.PUBLIC_SOURCE,
        original_url="javascript:alert(1)",
        checked_at=NOW,
        files=(OpportunityFile("x.hwp", "javascript:alert(2)"),),
    )
    world["catalog"].records[record.id] = record
    detail = world["service"].get_public(record.id)
    assert detail.original_url is None and detail.files[0].original_url is None
    assert detail.needs_verification is True


def test_public_source_with_checked_link_is_not_flagged(world):
    record = make_opportunity(source_kind=SourceKind.PUBLIC_SOURCE, checked_at=NOW)
    world["catalog"].records[record.id] = record
    assert world["service"].get_public(record.id).needs_verification is False


# ---- saved preparation ----


def test_save_is_idempotent_one_row(world):
    service, oid = world["service"], world["scholarship"].id
    first, created = service.save(USER_A, oid, SaveOpportunityRequest(memo="  메모 "))
    again, created_again = service.save(USER_A, oid, SaveOpportunityRequest(memo="다른 메모"))
    assert created and not created_again
    assert first == again and first.memo == "메모" and first.status is S.INTERESTED
    assert len(world["store"].saved) == 1


@pytest.mark.parametrize("key", ["draft", "missing"])
def test_cannot_save_non_public(world, key):
    oid = world["draft"].id if key == "draft" else uuid4()
    with pytest.raises(ApiError) as exc:
        world["service"].save(USER_A, oid, SaveOpportunityRequest())
    assert code_of(exc) == ErrorCode.NOT_FOUND


def test_owner_isolation_for_every_operation(world):
    service, oid = world["service"], world["scholarship"].id
    service.save(USER_A, oid, SaveOpportunityRequest())
    check, _ = service.add_check(
        USER_A, oid, CheckItemCreate(text="추천서", sort_order=0), "key-0001"
    )
    assert service.list_saved(USER_B) == []
    attempts = [
        lambda: service.update(USER_B, oid, SavedOpportunityPatch(memo="x"), 1),
        lambda: service.delete(USER_B, oid, 1),
        lambda: service.add_check(USER_B, oid, CheckItemCreate(text="x", sort_order=1), "key-0002"),
        lambda: service.update_check(USER_B, oid, check.id, CheckItemPatch(completed=True), 1),
        lambda: service.delete_check(USER_B, oid, check.id, 1),
    ]
    for attempt in attempts:
        with pytest.raises(ApiError) as exc:
            attempt()
        assert code_of(exc) == ErrorCode.NOT_FOUND
    assert service.list_saved(USER_A)[0].checks[0].completed_at is None


def test_full_state_flow_and_self_report(world):
    service, oid = world["service"], world["scholarship"].id
    service.save(USER_A, oid, SaveOpportunityRequest())
    preparing = service.update(USER_A, oid, SavedOpportunityPatch(status=S.PREPARING), 1)
    reported = service.update(
        USER_A, oid, SavedOpportunityPatch(status=S.SELF_REPORTED_SUBMITTED), 2
    )
    assert preparing.revision == 2 and reported.revision == 3
    assert reported.self_reported_submitted_at == NOW
    corrected = service.update(USER_A, oid, SavedOpportunityPatch(status=S.PREPARING), 3)
    assert corrected.self_reported_submitted_at is None
    assert [e.correction for e in world["store"].events] == [False, False, True]


def test_closed_keeps_self_report_timestamp_and_is_terminal(world):
    service, oid = world["service"], world["scholarship"].id
    service.save(USER_A, oid, SaveOpportunityRequest())
    service.update(USER_A, oid, SavedOpportunityPatch(status=S.PREPARING), 1)
    service.update(USER_A, oid, SavedOpportunityPatch(status=S.SELF_REPORTED_SUBMITTED), 2)
    closed = service.update(USER_A, oid, SavedOpportunityPatch(status=S.CLOSED), 3)
    assert closed.self_reported_submitted_at == NOW
    for target in (S.INTERESTED, S.PREPARING, S.SELF_REPORTED_SUBMITTED):
        with pytest.raises(ApiError) as exc:
            service.update(USER_A, oid, SavedOpportunityPatch(status=target), 4)
        assert code_of(exc) == ErrorCode.CONFLICT


def test_cannot_jump_to_self_report_from_interested(world):
    service, oid = world["service"], world["scholarship"].id
    service.save(USER_A, oid, SaveOpportunityRequest())
    with pytest.raises(ApiError) as exc:
        service.update(USER_A, oid, SavedOpportunityPatch(status=S.SELF_REPORTED_SUBMITTED), 1)
    assert code_of(exc) == ErrorCode.CONFLICT


def test_info_only_cannot_be_self_reported(world):
    service, oid = world["service"], world["info"].id
    service.save(USER_A, oid, SaveOpportunityRequest())
    service.update(USER_A, oid, SavedOpportunityPatch(status=S.PREPARING), 1)
    with pytest.raises(ApiError) as exc:
        service.update(USER_A, oid, SavedOpportunityPatch(status=S.SELF_REPORTED_SUBMITTED), 2)
    assert code_of(exc) == ErrorCode.CONFLICT


def test_transition_table_never_allows_leaving_closed():
    assert ALLOWED_TRANSITIONS[S.CLOSED] == frozenset()
    assert S.SELF_REPORTED_SUBMITTED not in ALLOWED_TRANSITIONS[S.INTERESTED]
    assert set(ALLOWED_TRANSITIONS) == set(S)


def test_stale_revision_and_race_conflict(world):
    service, store, oid = world["service"], world["store"], world["scholarship"].id
    service.save(USER_A, oid, SaveOpportunityRequest())
    with pytest.raises(ApiError) as exc:
        service.update(USER_A, oid, SavedOpportunityPatch(memo="x"), 2)
    assert code_of(exc) == ErrorCode.CONFLICT

    class RacingStore(FakeStore):
        def compare_and_set(self, record, expected_revision):
            return False

    racing = RacingStore()
    racing.saved = store.saved
    racing_service = OpportunityService(world["catalog"], racing, clock=lambda: NOW)
    with pytest.raises(ApiError) as exc:
        racing_service.update(USER_A, oid, SavedOpportunityPatch(memo="y"), 1)
    assert code_of(exc) == ErrorCode.CONFLICT


def test_noop_patch_does_not_bump_revision(world):
    service, oid = world["service"], world["scholarship"].id
    service.save(USER_A, oid, SaveOpportunityRequest(memo="같음"))
    assert service.update(USER_A, oid, SavedOpportunityPatch(memo="같음"), 1).revision == 1


def test_delete_removes_checks(world):
    service, store, oid = world["service"], world["store"], world["scholarship"].id
    service.save(USER_A, oid, SaveOpportunityRequest())
    service.add_check(USER_A, oid, CheckItemCreate(text="서류", sort_order=0), "key-0001")
    with pytest.raises(ApiError):
        service.delete(USER_A, oid, 9)
    service.delete(USER_A, oid, 1)
    assert store.saved == {} and store.checks == {}
    assert service.list_saved(USER_A) == []


def test_saved_view_hides_unpublished_source(world):
    service, oid = world["service"], world["scholarship"].id
    service.save(USER_A, oid, SaveOpportunityRequest())
    from dataclasses import replace

    catalog = world["catalog"]
    catalog.records[oid] = replace(catalog.records[oid], status=PublicationStatus.ARCHIVED)
    assert service.list_saved(USER_A)[0].opportunity is None


def test_store_absent_fails_closed(world):
    public_only = OpportunityService(world["catalog"], clock=lambda: NOW)
    with pytest.raises(ApiError) as exc:
        public_only.list_saved(USER_A)
    assert code_of(exc) == ErrorCode.UNAVAILABLE


# ---- checklist ----


def test_checklist_crud_and_ordering(world):
    service, oid = world["service"], world["scholarship"].id
    service.save(USER_A, oid, SaveOpportunityRequest())
    b, _ = service.add_check(USER_A, oid, CheckItemCreate(text="B", sort_order=2), "key-000b")
    a, _ = service.add_check(USER_A, oid, CheckItemCreate(text="A", sort_order=1), "key-000a")
    assert [c.text for c in service.list_saved(USER_A)[0].checks] == ["A", "B"]
    done = service.update_check(USER_A, oid, a.id, CheckItemPatch(completed=True), 1)
    assert done.completed_at == NOW and done.revision == 2
    undone = service.update_check(USER_A, oid, a.id, CheckItemPatch(completed=False), 2)
    assert undone.completed_at is None and undone.revision == 3
    with pytest.raises(ApiError) as exc:
        service.update_check(USER_A, oid, a.id, CheckItemPatch(sort_order=2), 3)
    assert code_of(exc) == ErrorCode.CONFLICT
    service.delete_check(USER_A, oid, b.id, 1)
    assert [c.id for c in service.list_saved(USER_A)[0].checks] == [a.id]


def test_check_idempotency_key(world):
    service, oid = world["service"], world["scholarship"].id
    service.save(USER_A, oid, SaveOpportunityRequest())
    body = CheckItemCreate(text="성적증명서", sort_order=0)
    first, created = service.add_check(USER_A, oid, body, "key-same")
    again, created_again = service.add_check(USER_A, oid, body, "key-same")
    assert created and not created_again and first == again
    assert len(world["store"].checks) == 1
    with pytest.raises(ApiError) as exc:
        service.add_check(USER_A, oid, CheckItemCreate(text="다름", sort_order=1), "key-same")
    assert code_of(exc) == ErrorCode.CONFLICT


def test_check_duplicate_sort_and_limit(world, monkeypatch):
    service, oid = world["service"], world["scholarship"].id
    service.save(USER_A, oid, SaveOpportunityRequest())
    service.add_check(USER_A, oid, CheckItemCreate(text="A", sort_order=0), "key-0001")
    with pytest.raises(ApiError):
        service.add_check(USER_A, oid, CheckItemCreate(text="B", sort_order=0), "key-0002")
    monkeypatch.setattr("app.features.opportunities.service.MAX_CHECKS_PER_SAVED", 1)
    with pytest.raises(ApiError) as exc:
        service.add_check(USER_A, oid, CheckItemCreate(text="C", sort_order=5), "key-0003")
    assert code_of(exc) == ErrorCode.CONFLICT


def test_check_in_other_saved_is_not_found(world):
    service = world["service"]
    s_id, c_id = world["scholarship"].id, world["contest"].id
    service.save(USER_A, s_id, SaveOpportunityRequest())
    service.save(USER_A, c_id, SaveOpportunityRequest())
    check, _ = service.add_check(USER_A, s_id, CheckItemCreate(text="A", sort_order=0), "key-0001")
    with pytest.raises(ApiError) as exc:
        service.update_check(USER_A, c_id, check.id, CheckItemPatch(text="x"), 1)
    assert code_of(exc) == ErrorCode.NOT_FOUND


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "", "sort_order": 0},
        {"text": "   ", "sort_order": 0},
        {"text": "x" * 201, "sort_order": 0},
        {"text": "a", "sort_order": -1},
        {"text": "a", "sort_order": 1000},
        {"text": "a", "sort_order": 0, "user_id": str(USER_B)},
    ],
)
def test_check_input_validation(payload):
    with pytest.raises(ValidationError):
        CheckItemCreate(**payload)


def test_patch_rejects_identity_and_unknown_status():
    with pytest.raises(ValidationError):
        SavedOpportunityPatch(status="submitted")
    with pytest.raises(ValidationError):
        SavedOpportunityPatch(user_id=str(USER_B))
    with pytest.raises(ValidationError):
        SaveOpportunityRequest(memo="x" * 1001)
