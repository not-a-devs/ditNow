"""Test-only fake contracts: never runtime storage or proof of MariaDB isolation."""

import copy
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.campus.domain import (
    Audience,
    AudienceType,
    CampusActor,
    Membership,
    Notice,
    NoticeStatus,
)
from app.features.notice_discussion.models import (
    AttachmentMetadata,
    Content,
    QuestionInput,
    RevisionMetadata,
)
from app.features.notice_discussion.ports import CurrentAccess
from app.features.notice_discussion.router import get_actor, get_service, router
from app.features.notice_discussion.service import NoticeDiscussionService
from app.schemas.common import ErrorCode

NOW = datetime(2026, 10, 30, tzinfo=UTC)
ACTOR, OTHER, DEPT, ELSEWHERE, NOTICE = (uuid4() for _ in range(5))
KEY = "review-stable-key-0001"


class FakeStore:
    def __init__(self):
        self.items, self.claims, self.locks = {}, {}, []
        self.lock = RLock()
        self.access = {
            actor: CurrentAccess(
                CampusActor(actor, (Membership(DEPT, 2),)), True, True, frozenset({DEPT})
            )
            for actor in (ACTOR, OTHER)
        }
        self.notice_rows = {
            NOTICE: Notice(
                NOTICE,
                Audience(AudienceType.DEPARTMENT, DEPT),
                "가상 공지",
                "가상 안내",
                NoticeStatus.PUBLISHED,
                2,
                OTHER,
                NOW,
                NOW,
                NOW,
            )
        }

    @contextmanager
    def unit_of_work(self, actor):
        with self.lock:
            before = copy.deepcopy((self.items, self.claims))
            store = self

            class Notices:
                def get(self, id):
                    return store.notice_rows.get(id)

                def list_released_for(self, audiences, limit):
                    return list(store.notice_rows.values())[:limit]

            class Uow:
                notices = Notices()

                def current_access(self):
                    return store.access.get(actor)

                def notice_attachments(self, id, revision):
                    return [AttachmentMetadata(id=uuid4(), filename="가상안내.pdf", size_bytes=123)]

                def notice_history(self, id, revision):
                    return [
                        RevisionMetadata(revision=1, changed_at=NOW, event="CREATED"),
                        RevisionMetadata(revision=3, changed_at=NOW, event="CONTENT_REVISED"),
                    ]

                def lock_question(self, id):
                    store.locks.append(id)

                def get(self, id):
                    return store.items.get(id)

                def list_questions(self, department, offset, limit):
                    return [
                        r
                        for r in store.items.values()
                        if r.department_id == department
                        and r.kind == "QUESTION"
                        and r.status == "ACTIVE"
                    ][offset : offset + limit]

                def list_comments(self, question, offset, limit):
                    return [
                        r
                        for r in store.items.values()
                        if r.question_id == question and r.status == "ACTIVE"
                    ][offset : offset + limit]

                def find_claim(self, namespace):
                    return store.claims.get(namespace)

                def insert(self, row, claim):
                    if claim.namespace in store.claims:
                        raise ApiError(ErrorCode.CONFLICT)
                    if row.question_id is not None:
                        assert row.question_id in store.locks
                    store.items[row.id] = row
                    store.claims[claim.namespace] = claim
                    if getattr(store, "fail_after_insert", False):
                        raise RuntimeError("fictional transaction failure")

                def compare_and_set(self, row, revision):
                    current = store.items[row.id]
                    assert (row.question_id or row.id) in store.locks
                    if (
                        current.revision != revision
                        or current.owner_id != actor
                        or current.status != "ACTIVE"
                    ):
                        raise ApiError(ErrorCode.CONFLICT)
                    store.items[row.id] = row

            try:
                yield Uow()
            except BaseException:
                self.items, self.claims = before
                raise


@pytest.fixture
def context():
    store = FakeStore()
    return store, NoticeDiscussionService(store, clock=lambda: NOW)


def question(service, key=KEY):
    return service.create(ACTOR, DEPT, QuestionInput(title="가상 질문", body="가상 내용"), key)


def test_notice_original_and_metadata_do_not_expose_author_or_storage(context):
    store, service = context
    result = service.notice(ACTOR, NOTICE)
    assert result.body == store.notice_rows[NOTICE].body
    assert [h.revision for h in result.history] == [1]
    raw = result.model_dump_json()
    assert "author_id" not in raw and str(OTHER) not in raw and "download" not in raw
    assert result.attachments[0].storage == "NOT_CONNECTED"
    assert len(service.notices(ACTOR, "가상")) == 1
    assert service.notices(ACTOR, "없는 말") == []


def test_current_membership_change_hides_notice_and_questions(context):
    store, service = context
    q = question(service)
    store.access[ACTOR] = CurrentAccess(
        CampusActor(ACTOR, (Membership(ELSEWHERE, 1),)), True, True, frozenset({ELSEWHERE})
    )
    for operation in [
        lambda: service.notice(ACTOR, NOTICE),
        lambda: service.items(ACTOR, DEPT),
        lambda: question(service),
        lambda: service.change(ACTOR, DEPT, q.id, 1, None),
    ]:
        with pytest.raises(ApiError) as error:
            operation()
        assert error.value.code == ErrorCode.NOT_FOUND


@pytest.mark.parametrize(
    "active,demo,expected",
    [(False, True, ErrorCode.UNAUTHORIZED), (True, False, ErrorCode.FORBIDDEN)],
)
def test_current_access_not_token_or_mock_login(context, active, demo, expected):
    store, service = context
    old = store.access[ACTOR]
    store.access[ACTOR] = CurrentAccess(old.actor, active, demo, old.student_departments)
    with pytest.raises(ApiError) as error:
        question(service)
    assert error.value.code == expected


def test_question_cas_ownership_and_private_projection(context):
    store, service = context
    q = question(service)
    other = service.items(OTHER, DEPT).items[0]
    assert (
        not other.is_mine
        and "owner_id" not in other.model_dump_json()
        and str(ACTOR) not in other.model_dump_json()
    )
    with pytest.raises(ApiError) as error:
        service.change(OTHER, DEPT, q.id, 1, None)
    assert error.value.code == ErrorCode.NOT_FOUND
    saved = service.change(ACTOR, DEPT, q.id, 1, QuestionInput(title="수정", body="새 내용"))
    assert saved.revision == 2
    with pytest.raises(ApiError) as error:
        service.change(ACTOR, DEPT, q.id, 1, None)
    assert error.value.code == ErrorCode.CONFLICT
    assert store.items[q.id].body == "새 내용"


def test_idempotency_body_conflict_and_tombstone(context):
    store, service = context
    first = question(service)
    assert question(service).id == first.id and len(store.items) == len(store.claims) == 1
    with pytest.raises(ApiError) as error:
        service.create(ACTOR, DEPT, QuestionInput(title="다른 내용", body="내용"), KEY)
    assert error.value.code == ErrorCode.CONFLICT
    service.change(ACTOR, DEPT, first.id, 1, None)
    assert store.items[first.id].status == "DELETED" and store.items[first.id].body == ""
    assert service.items(ACTOR, DEPT).items == []
    with pytest.raises(ApiError):
        question(service)


def test_comment_parent_lock_and_deleted_parent_are_required(context):
    store, service = context
    q = question(service)
    comment = service.create(OTHER, DEPT, Content(body="가상 댓글"), KEY, q.id)
    assert q.id in store.locks and comment.question_id == q.id
    assert len(service.items(ACTOR, DEPT, q.id).items) == 1
    changed = service.change(OTHER, DEPT, comment.id, 1, Content(body="수정 댓글"))
    assert changed.revision == 2
    service.change(ACTOR, DEPT, q.id, 1, None)
    for operation in [
        lambda: service.items(OTHER, DEPT, q.id),
        lambda: service.create(OTHER, DEPT, Content(body="다시"), KEY, q.id),
        lambda: service.change(OTHER, DEPT, comment.id, 2, None),
    ]:
        with pytest.raises(ApiError) as error:
            operation()
        assert error.value.code == ErrorCode.NOT_FOUND


def test_claim_and_item_both_roll_back_after_injected_failure(context):
    store, service = context
    store.fail_after_insert = True
    with pytest.raises(RuntimeError):
        question(service)
    assert store.items == {} and store.claims == {}


def test_parent_department_and_current_identity_are_not_client_claims(context):
    store, service = context
    q = question(service)
    old = store.access[OTHER]
    store.access[OTHER] = CurrentAccess(
        CampusActor(OTHER, (Membership(ELSEWHERE, 1),)), True, True, frozenset({ELSEWHERE})
    )
    with pytest.raises(ApiError) as error:
        service.create(OTHER, ELSEWHERE, Content(body="가상 타학과 댓글"), KEY, q.id)
    assert error.value.code == ErrorCode.NOT_FOUND
    store.access[OTHER] = CurrentAccess(old.actor, False, True, old.student_departments)
    with pytest.raises(ApiError) as error:
        service.create(OTHER, DEPT, Content(body="권한 폐기 후"), KEY, q.id)
    assert error.value.code == ErrorCode.UNAUTHORIZED


@pytest.mark.parametrize("filename", ["../a.pdf", "C:\\private.pdf", "secret\n.pdf", "  "])
def test_attachment_metadata_rejects_paths_and_control_characters(filename):
    with pytest.raises(ValidationError):
        AttachmentMetadata(id=uuid4(), filename=filename, size_bytes=1)


def app(context=None):
    application = create_app(Settings(environment="test"))
    application.include_router(router, prefix="/api/v1")
    if context is not None:
        application.dependency_overrides[get_actor] = lambda: ACTOR
        application.dependency_overrides[get_service] = lambda: context[1]
    return application


def test_default_dependencies_fail_closed_and_do_not_publish_global_routes():
    with TestClient(app()) as client:
        response = client.get("/api/v1/notice-discussion/notices")
        assert (
            response.status_code == 503 and response.headers["cache-control"] == "private, no-store"
        )
    assert not any(
        "notice-discussion" in p
        for p in create_app(Settings(environment="test")).openapi()["paths"]
    )


def test_http_crud_validation_private_errors_and_no_author(context):
    base = f"/api/v1/notice-discussion/departments/{DEPT}"
    with TestClient(app(context)) as client:
        body = {"title": "가상", "body": "내용"}
        response = client.post(base + "/questions", json=body, headers={"Idempotency-Key": KEY})
        assert (
            response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
        )
        id = response.json()["data"]["id"]
        assert "owner_id" not in response.text and str(ACTOR) not in response.text
        bad = client.post(
            base + "/questions",
            json=body | {"owner_id": str(OTHER)},
            headers={"Idempotency-Key": KEY},
        )
        assert bad.status_code == 400 and bad.headers["cache-control"] == "private, no-store"
        assert client.post(base + "/questions", json=body).status_code == 400
        assert client.delete(base + f"/items/{id}?expected_revision=1").json()["data"] is None
        assert client.get(base + "/questions").json()["data"]["items"] == []


def test_bad_storage_exception_never_echoes_body_or_secret(context, monkeypatch, caplog):
    def fail(*args):
        raise RuntimeError("fictional-password-and-private-question")

    monkeypatch.setattr(context[1], "notices", fail)
    with TestClient(app(context), raise_server_exceptions=False) as client:
        response = client.get("/api/v1/notice-discussion/notices")
        assert (
            response.status_code == 500 and response.headers["cache-control"] == "private, no-store"
        )
        assert "fictional-password" not in response.text and "private-question" not in caplog.text
