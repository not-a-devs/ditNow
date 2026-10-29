"""FR-LMS-001/002/003 scoped UOW contract tests; not a MariaDB adapter."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.online_learning.models import (
    Answer,
    DemoLearningPolicy,
    EnrollmentGrant,
    ExamRecord,
    LearningActor,
    LearningStep,
    OfferingRef,
    Option,
    ProgressInput,
    QuestionRecord,
    StartInput,
    SubmitInput,
    Unit,
)
from app.features.online_learning.router import get_learning_actor, get_learning_service, router
from app.features.online_learning.service import OnlineLearningService
from app.schemas.common import ErrorCode

NOW = datetime(2026, 10, 30, 0, 0, tzinfo=UTC)
STUDENT, OTHER, OUTSIDER = (LearningActor(user_id=uuid4()) for _ in range(3))
OFFERING, TERM, FOREIGN, UNIT, EXAM, STEP1, STEP2, QUESTION, OPTION1, OPTION2 = (
    uuid4() for _ in range(10)
)
KEY = "intent-key-00000001"


class TestStore:
    __test__ = False

    def __init__(self):
        self.lock = RLock()
        self.offering = OfferingRef(
            id=OFFERING, term_id=TERM, title="가상 온라인 강의", section="가상 A"
        )
        self.grants = {
            actor.user_id: EnrollmentGrant(
                active=True, current_student=True, offering_id=OFFERING, term_id=TERM
            )
            for actor in (STUDENT, OTHER)
        }
        self.policy = DemoLearningPolicy(
            offering_id=OFFERING,
            term_id=TERM,
            revision=1,
            completion_steps=2,
            max_attempts=2,
            require_all_answers=True,
        )
        self.units = {
            UNIT: Unit(
                id=UNIT,
                offering_id=OFFERING,
                title="가상 텍스트 학습",
                revision=1,
                status="published",
                opens_at=NOW - timedelta(hours=1),
                closes_at=NOW + timedelta(hours=1),
                steps=[
                    LearningStep(id=STEP1, text="가상 학습 단계 A"),
                    LearningStep(id=STEP2, text="가상 학습 단계 B"),
                ],
            )
        }
        self.exams = {
            EXAM: ExamRecord(
                id=EXAM,
                offering_id=OFFERING,
                title="가상 선택 시험",
                revision=1,
                status="published",
                opens_at=NOW - timedelta(hours=1),
                closes_at=NOW + timedelta(hours=1),
                questions=[
                    QuestionRecord(
                        id=QUESTION,
                        prompt="가상 선택지를 고르세요",
                        options=[
                            Option(id=OPTION1, text="가상 선택 A"),
                            Option(id=OPTION2, text="가상 선택 B"),
                        ],
                        correct_option_id=OPTION1,
                    )
                ],
                private_rubric="PRIVATE-RUBRIC-SENTINEL",
            )
        }
        self.progress = {}
        self.attempts = {}
        self.keys = {}
        self.events = []
        self.fail_after_write = False

    def my_offering_ids(self, user_id, limit):
        return [OFFERING] if user_id in self.grants else []

    @contextmanager
    def transaction(self, user_id, offering_id):
        with self.lock:
            if offering_id != OFFERING:
                raise ApiError(ErrorCode.FORBIDDEN)
            snapshot = deepcopy((self.progress, self.attempts, self.keys, self.events))
            try:
                yield TestTransaction(self, user_id)
            except Exception:
                self.progress, self.attempts, self.keys, self.events = snapshot
                raise


class TestTransaction:
    __test__ = False

    def __init__(self, store, user):
        self.store, self.user = store, user
        self.offering, self.policy = store.offering, store.policy
        self.grant = store.grants.get(
            user,
            EnrollmentGrant(
                active=False, current_student=False, offering_id=OFFERING, term_id=TERM
            ),
        )

    def units(self):
        return list(self.store.units.values())

    def unit(self, id):
        return self.store.units.get(id)

    def progress(self, id):
        return self.store.progress.get((self.user, id))

    def exams(self):
        return list(self.store.exams.values())

    def exam(self, id):
        return self.store.exams.get(id)

    def attempts(self):
        return list(self.store.attempts.values())

    def attempt(self, id):
        return self.store.attempts.get(id)

    def replay(self, op, key, body_hash):
        saved = self.store.keys.get((self.user, OFFERING, op, key))
        if saved and saved[0] != body_hash:
            raise ApiError(ErrorCode.CONFLICT)
        return saved[1] if saved else None

    def _event(self, id, op, key, body_hash):
        self.store.events.append((self.user, op, id))
        self.store.keys[self.user, OFFERING, op, key] = (body_hash, id)
        if self.store.fail_after_write:
            raise RuntimeError("test atomic rollback")

    def save_progress(self, row, expected_revision, op, key, body_hash):
        assert row.owner_id == self.user and row.offering_id == OFFERING
        old = self.progress(row.unit_id)
        if expected_revision != (old.revision if old else 0):
            raise ApiError(ErrorCode.CONFLICT)
        self.store.progress[self.user, row.unit_id] = row
        self._event(row.unit_id, op, key, body_hash)
        return row

    def start(self, row, op, key, body_hash):
        assert row.owner_id == self.user and row.offering_id == OFFERING
        self.store.attempts[row.id] = row
        self._event(row.id, op, key, body_hash)
        return row

    def submit(self, row, expected_revision, op, key, body_hash):
        assert row.owner_id == self.user and row.offering_id == OFFERING
        old = self.attempt(row.id)
        if old is None or old.revision != expected_revision:
            raise ApiError(ErrorCode.CONFLICT)
        self.store.attempts[row.id] = row
        self._event(row.id, op, key, body_hash)
        return row


@pytest.fixture
def setup():
    store = TestStore()
    return store, OnlineLearningService(store, clock=lambda: NOW)


def assert_code(code, call):
    with pytest.raises(ApiError) as exc:
        call()
    assert exc.value.code == code


def start(service, actor=STUDENT, key=KEY):
    return service.start(
        actor, OFFERING, EXAM, StartInput(expected_exam_revision=1, expected_policy_revision=1), key
    )


def progress(step=STEP1, revision=0):
    return ProgressInput(
        step_id=step,
        expected_revision=revision,
        expected_unit_revision=1,
        expected_policy_revision=1,
    )


def answers(revision=1):
    return SubmitInput(
        expected_exam_revision=1,
        expected_policy_revision=1,
        expected_revision=revision,
        answers=[Answer(question_id=QUESTION, option_id=OPTION2)],
    )


def test_workspace_filters_drafts_and_cross_parent_and_other_student_attempts(setup):
    store, service = setup
    start(service, OTHER)
    store.units[uuid4()] = store.units[UNIT].model_copy(update={"offering_id": FOREIGN})
    store.exams[uuid4()] = store.exams[EXAM].model_copy(update={"status": "draft"})
    workspace = service.workspace(STUDENT, OFFERING)
    assert len(workspace.units) == len(workspace.exams) == 1
    assert workspace.attempts == []
    assert workspace.offering.term_id == TERM
    serialized = workspace.model_dump_json()
    assert all(
        value not in serialized
        for value in ("correct_option_id", "PRIVATE-RUBRIC", "owner_id", "password")
    )


def test_step_progress_is_self_reported_demo_and_idempotent(setup):
    store, service = setup
    one = service.mark_step(STUDENT, OFFERING, UNIT, progress(), KEY)
    assert one.state == "IN_PROGRESS" and one.revision == 1
    assert service.mark_step(STUDENT, OFFERING, UNIT, progress(), KEY) == one
    two = service.mark_step(STUDENT, OFFERING, UNIT, progress(STEP2, 1), KEY + "2")
    assert two.state == "DEMO_COMPLETED" and two.official_attendance == "BLOCKED"
    assert two.evidence == "SELF_REPORTED_DEMO"
    assert len(store.events) == 2
    assert service.workspace(OTHER, OFFERING).progress[0].completed_steps == []


def test_step_changed_key_payload_cas_unknown_step_and_parent(setup):
    store, service = setup
    service.mark_step(STUDENT, OFFERING, UNIT, progress(), KEY)
    assert_code(
        ErrorCode.CONFLICT, lambda: service.mark_step(STUDENT, OFFERING, UNIT, progress(STEP2), KEY)
    )
    assert_code(
        ErrorCode.CONFLICT,
        lambda: service.mark_step(STUDENT, OFFERING, UNIT, progress(STEP2), KEY + "2"),
    )
    assert_code(
        ErrorCode.VALIDATION,
        lambda: service.mark_step(STUDENT, OFFERING, UNIT, progress(uuid4(), 1), KEY + "3"),
    )
    store.units[UNIT] = store.units[UNIT].model_copy(update={"offering_id": FOREIGN})
    assert_code(
        ErrorCode.NOT_FOUND, lambda: service.mark_step(STUDENT, OFFERING, UNIT, progress(), KEY)
    )


@pytest.mark.parametrize(
    "change", ["inactive", "not_student", "term", "policy_parent", "missing_policy"]
)
def test_current_enrollment_and_policy_are_required_for_reads_and_replays(setup, change):
    store, service = setup
    attempt = start(service)
    if change == "inactive":
        store.grants[STUDENT.user_id].active = False
    elif change == "not_student":
        store.grants[STUDENT.user_id].current_student = False
    elif change == "term":
        store.grants[STUDENT.user_id].term_id = uuid4()
    elif change == "policy_parent":
        store.policy.offering_id = uuid4()
    else:
        store.policy = None
    code = (
        ErrorCode.UNAVAILABLE
        if change in {"policy_parent", "missing_policy"}
        else ErrorCode.FORBIDDEN
    )
    for call in [
        lambda: service.workspace(STUDENT, OFFERING),
        lambda: start(service),
        lambda: service.attempt(STUDENT, OFFERING, EXAM, attempt.id),
    ]:
        assert_code(code, call)


def test_other_student_guessed_attempt_and_cross_offering_are_rejected(setup):
    _, service = setup
    attempt = start(service)
    assert_code(ErrorCode.NOT_FOUND, lambda: service.attempt(OTHER, OFFERING, EXAM, attempt.id))
    assert_code(
        ErrorCode.NOT_FOUND,
        lambda: service.submit(OTHER, OFFERING, EXAM, attempt.id, answers(), KEY),
    )
    assert_code(ErrorCode.FORBIDDEN, lambda: service.workspace(OUTSIDER, OFFERING))
    assert_code(ErrorCode.FORBIDDEN, lambda: service.workspace(STUDENT, FOREIGN))


def test_public_exam_and_attempt_projection_never_expose_keys_or_grading(setup):
    store, service = setup
    exam = service.exam(STUDENT, OFFERING, EXAM)
    attempt = start(service)
    submitted = service.submit(STUDENT, OFFERING, EXAM, attempt.id, answers(), KEY)
    assert submitted.state == "submitted" and submitted.evaluation == "NOT_GRADED"
    assert submitted.official_grade == "BLOCKED"
    assert store.attempts[attempt.id].answers[0].option_id == OPTION2
    serialized = exam.model_dump_json() + submitted.model_dump_json()
    assert all(
        key not in serialized
        for key in (
            "correct_option_id",
            "private_rubric",
            "PRIVATE-RUBRIC",
            "owner_id",
            "answers",
            "score",
        )
    )


def test_start_and_submit_exact_replays_and_changed_payloads(setup):
    store, service = setup
    first = start(service)
    assert start(service) == first
    assert_code(
        ErrorCode.CONFLICT,
        lambda: service.start(
            STUDENT,
            OFFERING,
            EXAM,
            StartInput(expected_exam_revision=2, expected_policy_revision=1),
            KEY,
        ),
    )
    done = service.submit(STUDENT, OFFERING, EXAM, first.id, answers(), KEY)
    assert service.submit(STUDENT, OFFERING, EXAM, first.id, answers(), KEY) == done
    changed = answers().model_copy(
        update={"answers": [Answer(question_id=QUESTION, option_id=OPTION1)]}
    )
    assert_code(
        ErrorCode.CONFLICT, lambda: service.submit(STUDENT, OFFERING, EXAM, first.id, changed, KEY)
    )
    assert len(store.events) == 2


def test_replay_never_revives_missing_or_withdrawn_parent(setup):
    store, service = setup
    first = start(service)
    service.submit(STUDENT, OFFERING, EXAM, first.id, answers(), KEY)
    store.exams[EXAM].status = "draft"
    assert_code(
        ErrorCode.NOT_FOUND,
        lambda: service.submit(STUDENT, OFFERING, EXAM, first.id, answers(), KEY),
    )
    store.exams[EXAM].status = "published"
    del store.attempts[first.id]
    assert_code(ErrorCode.NOT_FOUND, lambda: start(service))
    assert not store.attempts


@pytest.mark.parametrize("at", [NOW - timedelta(hours=2), NOW + timedelta(hours=1)])
def test_utc_window_is_start_inclusive_end_exclusive(setup, at):
    store, _ = setup
    service = OnlineLearningService(store, clock=lambda: at)
    assert_code(ErrorCode.CONFLICT, lambda: start(service))
    assert_code(
        ErrorCode.CONFLICT, lambda: service.mark_step(STUDENT, OFFERING, UNIT, progress(), KEY)
    )


def test_unit_policy_changes_do_not_reinterpret_existing_progress(setup):
    store, service = setup
    service.mark_step(STUDENT, OFFERING, UNIT, progress(), KEY)
    store.policy.revision = 2
    stale = service.workspace(STUDENT, OFFERING).progress[0]
    assert stale.state == "STALE_DEMO" and stale.completed_steps == []
    assert_code(
        ErrorCode.CONFLICT,
        lambda: service.mark_step(
            STUDENT,
            OFFERING,
            UNIT,
            progress(STEP2, 1).model_copy(update={"expected_policy_revision": 2}),
            KEY + "2",
        ),
    )


def test_policy_attempt_limit_and_one_active_attempt_are_enforced(setup):
    store, service = setup
    first = start(service)
    assert_code(ErrorCode.CONFLICT, lambda: start(service, key=KEY + "2"))
    service.submit(STUDENT, OFFERING, EXAM, first.id, answers(), KEY)
    second = start(service, key=KEY + "2")
    service.submit(STUDENT, OFFERING, EXAM, second.id, answers(), KEY)
    assert_code(ErrorCode.CONFLICT, lambda: start(service, key=KEY + "3"))
    assert len(store.attempts) == 2


def test_invalid_incomplete_and_stale_exam_submission(setup):
    store, service = setup
    first = start(service)
    for invalid in [[], [Answer(question_id=QUESTION, option_id=uuid4())]]:
        assert_code(
            ErrorCode.VALIDATION,
            lambda invalid=invalid: service.submit(
                STUDENT,
                OFFERING,
                EXAM,
                first.id,
                answers().model_copy(update={"answers": invalid}),
                KEY,
            ),
        )
    store.exams[EXAM].revision = 2
    assert_code(
        ErrorCode.CONFLICT,
        lambda: service.submit(STUDENT, OFFERING, EXAM, first.id, answers(), KEY),
    )
    assert store.attempts[first.id].state == "in_progress"


def test_uow_rolls_back_row_event_and_replay_together(setup):
    store, service = setup
    store.fail_after_write = True
    with pytest.raises(RuntimeError):
        start(service)
    assert not store.attempts and not store.keys and not store.events
    store.fail_after_write = False
    first = start(service)
    store.fail_after_write = True
    with pytest.raises(RuntimeError):
        service.submit(STUDENT, OFFERING, EXAM, first.id, answers(), KEY)
    assert store.attempts[first.id].state == "in_progress" and len(store.events) == 1


def test_concurrent_start_and_submit_are_serialized_by_test_uow(setup):
    store, service = setup

    def create(index):
        try:
            return start(service, key=KEY + str(index))
        except ApiError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(create, range(6)))
    assert sum(not isinstance(r, ErrorCode) for r in results) == 1
    assert len(store.attempts) == 1
    first = next(iter(store.attempts.values()))

    def send(index):
        try:
            return service.submit(STUDENT, OFFERING, EXAM, first.id, answers(), KEY + str(index))
        except ApiError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(send, range(6)))
    assert sum(not isinstance(r, ErrorCode) for r in results) == 1
    assert len(store.events) == 2


def test_naive_clock_and_unknown_server_owned_input_are_rejected(setup):
    store, _ = setup
    assert_code(
        ErrorCode.UNAVAILABLE,
        lambda: OnlineLearningService(store, clock=lambda: NOW.replace(tzinfo=None)).workspace(
            STUDENT, OFFERING
        ),
    )
    for field in ["owner_id", "score", "correct_option_id"]:
        with pytest.raises(ValidationError):
            SubmitInput(**answers().model_dump(), **{field: "fake"})
    with pytest.raises(ValidationError):
        SubmitInput(
            **answers().model_dump(exclude={"answers"}),
            answers=[Answer(question_id=QUESTION, option_id=OPTION1)] * 2,
        )


def client_for(service=None):
    app = create_app(Settings(environment="test"))
    app.include_router(router, prefix="/api/v1")
    if service:
        app.dependency_overrides[get_learning_actor] = lambda: STUDENT
        app.dependency_overrides[get_learning_service] = lambda: service
    return TestClient(app)


def test_router_is_unmounted_by_default_and_approval_dependencies_fail_closed():
    with TestClient(create_app(Settings(environment="test"))) as client:
        assert client.get("/api/v1/online-learning").status_code == 404
    with client_for() as client:
        response = client.get("/api/v1/online-learning")
        assert response.status_code == 503
        assert response.headers["cache-control"] == "private, no-store"


def test_identical_concurrent_start_retries_return_one_receipt_and_event(setup):
    store, service = setup
    with ThreadPoolExecutor(max_workers=6) as pool:
        receipts = list(pool.map(lambda _: start(service), range(6)))
    assert len({row.id for row in receipts}) == 1
    assert len(store.events) == len(store.attempts) == 1


def test_opening_boundary_and_closed_exam_receipt_do_not_expose_questions(setup):
    store, service = setup
    store.exams[EXAM].opens_at = NOW
    first = start(service)
    service.submit(STUDENT, OFFERING, EXAM, first.id, answers(), KEY)
    store.exams[EXAM].status = "closed"
    assert service.attempt(STUDENT, OFFERING, EXAM, first.id).state == "submitted"
    assert_code(ErrorCode.CONFLICT, lambda: service.exam(STUDENT, OFFERING, EXAM))


def test_http_mutation_lifecycle_uses_version_key_and_safe_projection(setup):
    _, service = setup
    with client_for(service) as client:
        base = f"/api/v1/online-learning/{OFFERING}"
        headers = {"Idempotency-Key": KEY}
        response = client.put(
            f"{base}/units/{UNIT}/progress",
            json=progress().model_dump(mode="json"),
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["official_attendance"] == "BLOCKED"
        response = client.post(
            f"{base}/exams/{EXAM}/attempts",
            json={"expected_exam_revision": 1, "expected_policy_revision": 1},
            headers=headers,
        )
        assert response.status_code == 200
        id = response.json()["data"]["id"]
        path = f"{base}/exams/{EXAM}/attempts/{id}/submit"
        done = client.post(path, json=answers().model_dump(mode="json"), headers=headers)
        assert done.status_code == 200
        assert done.json()["data"]["evaluation"] == "NOT_GRADED"
        assert done.headers["cache-control"] == "private, no-store"
        assert "answers" not in done.json()["data"]
        retry = client.post(path, json=answers().model_dump(mode="json"), headers=headers)
        assert retry.json()["data"] == done.json()["data"]


def test_http_private_projection_strict_uuid_and_input_validation(setup):
    _, service = setup
    with client_for(service) as client:
        paths = [
            f"/api/v1/online-learning/{OFFERING}",
            f"/api/v1/online-learning/{OFFERING}/exams/{EXAM}",
        ]
        for path in paths:
            response = client.get(path)
            assert (
                response.status_code == 200
                and response.headers["cache-control"] == "private, no-store"
            )
            assert (
                "PRIVATE-RUBRIC" not in response.text and "correct_option_id" not in response.text
            )
        response = client.get("/api/v1/online-learning/not-a-uuid")
        assert (
            response.status_code == 400 and response.headers["cache-control"] == "private, no-store"
        )
        path = f"/api/v1/online-learning/{OFFERING}/exams/{EXAM}/attempts"
        response = client.post(
            path,
            json={"expected_exam_revision": 1, "expected_policy_revision": 1, "score": 100},
            headers={"Idempotency-Key": KEY},
        )
        assert response.status_code == 400
        schema = client.app.openapi()
        assert all(
            name not in schema["components"]["schemas"]
            for name in ["ExamRecord", "QuestionRecord", "AttemptRecord"]
        )
