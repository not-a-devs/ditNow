import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.classrooms.models import (
    Assignment,
    ClassroomActor,
    ClassroomGrant,
    Material,
    Offering,
    QuestionChange,
    QuestionInput,
    QuestionRecord,
    SubmissionInput,
    SubmissionView,
)
from app.features.classrooms.router import get_classroom_actor, get_classroom_service, router
from app.features.classrooms.service import ClassroomService
from app.schemas.common import ErrorCode

NOW = datetime(2026, 10, 30, 0, 0, tzinfo=UTC)
STUDENT, OTHER, TEACHER, OUTSIDER = (ClassroomActor(user_id=uuid4()) for _ in range(4))
OFFERING, FOREIGN = uuid4(), uuid4()
ASSIGNMENT, DRAFT, CLOSED = uuid4(), uuid4(), uuid4()


class FakeStore:
    """Test-only transactional adapter; never installed in application runtime."""

    def __init__(self):
        self.lock = RLock()
        self.offering = Offering(
            id=OFFERING,
            title="가상 강의",
            term="가상 학기",
            section="A",
            instructor_name="가상 교수",
        )
        self.grants = {
            STUDENT.user_id: ClassroomGrant(active=True, role="student"),
            OTHER.user_id: ClassroomGrant(active=True, role="student"),
            TEACHER.user_id: ClassroomGrant(active=True, role="teacher"),
        }
        self.question_rows = {}
        self.keys = {}
        self.submission_rows = {}
        self.assignment_rows = [
            Assignment(
                id=id,
                title="가상 과제",
                instructions="가상 텍스트 제출",
                deadline_at=NOW + timedelta(hours=1),
                status=status,
                revision=1,
            )
            for id, status in [(ASSIGNMENT, "published"), (DRAFT, "draft"), (CLOSED, "closed")]
        ]

    def my_offering_ids(self, user_id, limit):
        return [OFFERING] if user_id in self.grants else []

    @contextmanager
    def transaction(self, user_id, offering_id):
        with self.lock:
            if offering_id != OFFERING:
                raise ApiError(ErrorCode.FORBIDDEN)
            yield FakeTransaction(self, user_id)


class FakeTransaction:
    def __init__(self, store, user_id):
        self.store = store
        self.user_id = user_id
        self.grant = store.grants.get(user_id, ClassroomGrant(active=False, role="student"))
        self.offering = store.offering

    def materials(self):
        return [
            Material(id=uuid4(), title="공개 참고자료", description="가상 자료"),
            Material(id=uuid4(), title="보관 자료", description="숨김", status="archived"),
        ]

    def assignments(self):
        return self.store.assignment_rows

    def questions(self):
        return list(self.store.question_rows.values())

    def my_submissions(self, author_id):
        assert author_id == self.user_id
        return [
            row
            for (assignment_id, owner), row in self.store.submission_rows.items()
            if owner == author_id
        ]

    def create_question(self, author_id, text, idempotency_key, now):
        key = author_id, idempotency_key
        if key in self.store.keys:
            row = self.store.question_rows[self.store.keys[key]]
            if row.text != text:
                raise ApiError(ErrorCode.CONFLICT)
            return row
        row = QuestionRecord(id=uuid4(), author_id=author_id, text=text, created_at=now, revision=1)
        self.store.question_rows[row.id] = row
        self.store.keys[key] = row.id
        return row

    def change_question(self, question_id, expected_revision, answer, resolve):
        row = self.store.question_rows[question_id]
        if row.revision != expected_revision:
            raise ApiError(ErrorCode.CONFLICT)
        changed = row.model_copy(
            update={
                "answer": row.answer if resolve else answer,
                "state": "resolved" if resolve else "answered",
                "revision": expected_revision + 1,
            }
        )
        self.store.question_rows[question_id] = changed
        return changed

    def submit_text(self, assignment_id, author_id, text, expected_revision, now):
        key = assignment_id, author_id
        previous = self.store.submission_rows.get(key)
        if expected_revision != (previous.revision if previous else 0):
            raise ApiError(ErrorCode.CONFLICT)
        row = SubmissionView(
            assignment_id=assignment_id,
            text=text,
            state="resubmitted" if previous else "submitted",
            submitted_at=now,
            revision=expected_revision + 1,
        )
        self.store.submission_rows[key] = row
        return row


@pytest.fixture
def setup():
    store = FakeStore()
    return store, ClassroomService(store, clock=lambda: NOW)


def assert_code(code, callback):
    with pytest.raises(ApiError) as exc:
        callback()
    assert exc.value.code == code


def test_workspace_filters_drafts_private_questions_and_submissions(setup):
    store, service = setup
    private = service.create_question(
        STUDENT, OFFERING, QuestionInput(text="비공개 질문"), "key-1234567890123"
    )
    service.submit_text(
        STUDENT, OFFERING, ASSIGNMENT, SubmissionInput(text="개인 과제", expected_revision=0)
    )
    own = service.workspace(STUDENT, OFFERING)
    assert own.questions[0].id == private.id
    assert len(own.submissions) == 1
    assert len(own.materials) == 1
    assert len(own.assignments) == 2
    other = service.workspace(OTHER, OFFERING)
    assert other.questions == [] and other.submissions == []
    encoded = own.model_dump_json()
    assert str(STUDENT.user_id) not in encoded and "author_id" not in encoded
    assert len(service.workspace(TEACHER, OFFERING).questions) == 1


def test_current_enrollment_revoked_and_cross_offering_denied(setup):
    store, service = setup
    assert service.list_offerings(STUDENT, 1)[0].id == OFFERING
    assert service.list_offerings(OUTSIDER, 25) == []
    assert_code(ErrorCode.FORBIDDEN, lambda: service.workspace(OUTSIDER, OFFERING))
    store.grants[STUDENT.user_id] = ClassroomGrant(active=False, role="student")
    assert_code(ErrorCode.FORBIDDEN, lambda: service.workspace(STUDENT, OFFERING))
    assert_code(ErrorCode.FORBIDDEN, lambda: service.workspace(TEACHER, FOREIGN))


def test_question_teacher_state_and_revision_rules(setup):
    store, service = setup
    q = service.create_question(STUDENT, OFFERING, QuestionInput(text="질문"), "key-1234567890123")
    answer = QuestionChange(text="답변", expected_revision=1)
    assert_code(ErrorCode.FORBIDDEN, lambda: service.answer_question(OTHER, OFFERING, q.id, answer))
    assert_code(ErrorCode.CONFLICT, lambda: service.resolve_question(TEACHER, OFFERING, q.id, 1))
    answered = service.answer_question(TEACHER, OFFERING, q.id, answer)
    assert answered.state == "answered" and answered.revision == 2
    assert_code(
        ErrorCode.CONFLICT, lambda: service.answer_question(TEACHER, OFFERING, q.id, answer)
    )
    assert service.resolve_question(TEACHER, OFFERING, q.id, 2).state == "resolved"
    assert_code(ErrorCode.CONFLICT, lambda: service.resolve_question(TEACHER, OFFERING, q.id, 2))


def test_teacher_assignment_is_revalidated_for_each_write(setup):
    store, service = setup
    question = service.create_question(
        STUDENT, OFFERING, QuestionInput(text="질문"), "key-1234567890123"
    )
    store.grants[TEACHER.user_id] = ClassroomGrant(active=False, role="teacher")
    assert_code(
        ErrorCode.FORBIDDEN,
        lambda: service.answer_question(
            TEACHER, OFFERING, question.id, QuestionChange(text="답변", expected_revision=1)
        ),
    )


def test_question_idempotency_and_parallel_requests(setup):
    store, service = setup

    def create(_):
        return service.create_question(
            STUDENT, OFFERING, QuestionInput(text="동일 질문"), "key-1234567890123"
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(create, range(8)))
    assert len({row.id for row in rows}) == 1 and len(store.question_rows) == 1
    assert_code(
        ErrorCode.CONFLICT,
        lambda: service.create_question(
            STUDENT, OFFERING, QuestionInput(text="다른 질문"), "key-1234567890123"
        ),
    )


def test_submission_deadline_utc_and_stale_revision(setup):
    store, service = setup
    first = service.submit_text(
        STUDENT, OFFERING, ASSIGNMENT, SubmissionInput(text="초안", expected_revision=0)
    )
    assert first.state == "submitted" and first.submitted_at == NOW
    assert_code(
        ErrorCode.CONFLICT,
        lambda: service.submit_text(
            STUDENT, OFFERING, ASSIGNMENT, SubmissionInput(text="경합", expected_revision=0)
        ),
    )
    second = service.submit_text(
        STUDENT, OFFERING, ASSIGNMENT, SubmissionInput(text="수정", expected_revision=1)
    )
    assert second.state == "resubmitted" and second.revision == 2
    assert_code(
        ErrorCode.NOT_FOUND,
        lambda: service.submit_text(
            STUDENT, OFFERING, DRAFT, SubmissionInput(text="숨김", expected_revision=0)
        ),
    )
    assert_code(
        ErrorCode.CONFLICT,
        lambda: service.submit_text(
            STUDENT, OFFERING, CLOSED, SubmissionInput(text="종료", expected_revision=0)
        ),
    )
    at_deadline = ClassroomService(store, clock=lambda: NOW + timedelta(hours=1))
    assert_code(
        ErrorCode.CONFLICT,
        lambda: at_deadline.submit_text(
            STUDENT, OFFERING, ASSIGNMENT, SubmissionInput(text="늦음", expected_revision=2)
        ),
    )
    assert_code(
        ErrorCode.FORBIDDEN,
        lambda: service.submit_text(
            TEACHER, OFFERING, ASSIGNMENT, SubmissionInput(text="교수 제출", expected_revision=0)
        ),
    )


def test_submission_parallel_revision_conflict(setup):
    store, service = setup

    def submit(_):
        try:
            service.submit_text(
                STUDENT, OFFERING, ASSIGNMENT, SubmissionInput(text="제출", expected_revision=0)
            )
            return "ok"
        except ApiError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=4) as pool:
        states = list(pool.map(submit, range(4)))
    assert states.count("ok") == 1 and states.count(ErrorCode.CONFLICT) == 3


def test_timezone_and_metadata_validation():
    with pytest.raises(ValidationError):
        Assignment(
            id=ASSIGNMENT,
            title="가상",
            instructions="지시",
            deadline_at="2026-10-30T10:00:00",
            status="published",
            revision=1,
        )
    row = Assignment(
        id=ASSIGNMENT,
        title="가상",
        instructions="지시",
        deadline_at="2026-10-30T10:00:00+09:00",
        status="published",
        revision=1,
    )
    assert row.deadline_at.hour == 1
    with pytest.raises(ValidationError):
        QuestionInput(text="   ")
    with pytest.raises(ValidationError):
        Material(
            id=uuid4(),
            title="가상",
            description="설명",
            public_reference_url="https://user:password@example.test/private",
        )


def test_router_unconfigured_fails_closed_and_snapshot_is_untouched():
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        result = client.get("/api/v1/classrooms")
    assert result.status_code == 503 and result.json()["code"] == "UNAVAILABLE"
    assert result.headers["Cache-Control"] == "private, no-store"


def test_router_fake_adapter_validation_and_safe_response(setup):
    store, service = setup
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_classroom_actor] = lambda: STUDENT
    app.dependency_overrides[get_classroom_service] = lambda: service
    assert "QuestionRecord" not in app.openapi()["components"]["schemas"]
    with TestClient(app) as client:
        invalid = client.get("/api/v1/classrooms?limit=101")
        assert invalid.status_code == 400
        assert invalid.headers["Cache-Control"] == "private, no-store"
        listing = client.get("/api/v1/classrooms")
        assert listing.status_code == 200
        assert listing.headers["Cache-Control"] == "private, no-store"
        assert client.get("/api/v1/classrooms/not-a-uuid").status_code == 400
        path = f"/api/v1/classrooms/{OFFERING}/questions"
        assert (
            client.post(
                path,
                json={"text": "질문", "role": "teacher"},
                headers={"Idempotency-Key": "key-1234567890123"},
            ).status_code
            == 400
        )
        assert client.post(path, json={"text": "질문"}).status_code == 400
        response = client.post(
            path, json={"text": "질문"}, headers={"Idempotency-Key": "key-1234567890123"}
        )
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "private, no-store"
        assert "author_id" not in response.text and str(STUDENT.user_id) not in response.text
        assert UUID(response.json()["data"]["id"])


def test_private_workspace_denial_is_not_cacheable(setup):
    store, service = setup
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_classroom_actor] = lambda: OUTSIDER
    app.dependency_overrides[get_classroom_service] = lambda: service
    with TestClient(app) as client:
        response = client.get(f"/api/v1/classrooms/{OFFERING}")
    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "private, no-store"
    assert "가상 강의" not in response.text


def test_unexpected_classroom_failure_is_redacted_and_not_cached(setup, caplog):
    store, service = setup

    def broken_ids(user_id, limit):
        raise RuntimeError("private-database-password")

    store.my_offering_ids = broken_ids
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_classroom_actor] = lambda: STUDENT
    app.dependency_overrides[get_classroom_service] = lambda: service
    with caplog.at_level(logging.ERROR, logger="ditnow.api"), TestClient(app) as client:
        response = client.get("/api/v1/classrooms")
    assert response.status_code == 500
    assert response.headers["Cache-Control"] == "private, no-store"
    assert "private-database-password" not in response.text
    own_logs = "\n".join(record.message for record in caplog.records if record.name == "ditnow.api")
    assert "private-database-password" not in own_logs
