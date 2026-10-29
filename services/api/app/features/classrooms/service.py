from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.core.errors import ApiError
from app.features.classrooms.models import (
    ClassroomActor,
    ClassroomWorkspace,
    Offering,
    QuestionChange,
    QuestionInput,
    QuestionRecord,
    QuestionView,
    SubmissionInput,
    SubmissionView,
)
from app.features.classrooms.ports import ClassroomStore, ClassroomTransaction
from app.schemas.common import ErrorCode


def utc_now() -> datetime:
    return datetime.now(UTC)


class ClassroomService:
    def __init__(self, store: ClassroomStore, clock: Callable[[], datetime] = utc_now):
        self.store = store
        self.clock = clock

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        return now.astimezone(UTC)

    @staticmethod
    def _access(tx: ClassroomTransaction, teacher: bool = False) -> None:
        if not tx.grant.active or (teacher and tx.grant.role != "teacher"):
            raise ApiError(ErrorCode.FORBIDDEN)

    @staticmethod
    def _question_view(record: QuestionRecord, actor: ClassroomActor) -> QuestionView:
        return QuestionView(
            **record.model_dump(exclude={"author_id"}), is_mine=record.author_id == actor.user_id
        )

    def list_offerings(self, actor: ClassroomActor, limit: int) -> list[Offering]:
        result = []
        for offering_id in self.store.my_offering_ids(actor.user_id, limit)[:limit]:
            with self.store.transaction(actor.user_id, offering_id) as tx:
                self._access(tx)
                result.append(tx.offering)
        return result

    def workspace(self, actor: ClassroomActor, offering_id: UUID) -> ClassroomWorkspace:
        with self.store.transaction(actor.user_id, offering_id) as tx:
            self._access(tx)
            questions = [
                self._question_view(q, actor)
                for q in tx.questions()
                if tx.grant.role == "teacher" or q.author_id == actor.user_id
            ]
            return ClassroomWorkspace(
                offering=tx.offering,
                role=tx.grant.role,
                materials=[m for m in tx.materials() if m.status == "published"],
                assignments=[
                    a for a in tx.assignments() if tx.grant.role == "teacher" or a.status != "draft"
                ],
                questions=questions,
                submissions=tx.my_submissions(actor.user_id) if tx.grant.role == "student" else [],
            )

    def create_question(
        self, actor: ClassroomActor, offering_id: UUID, body: QuestionInput, key: str
    ) -> QuestionView:
        with self.store.transaction(actor.user_id, offering_id) as tx:
            self._access(tx)
            if tx.grant.role != "student":
                raise ApiError(ErrorCode.FORBIDDEN)
            return self._question_view(
                tx.create_question(actor.user_id, body.text, key, self._now()), actor
            )

    def answer_question(
        self, actor: ClassroomActor, offering_id: UUID, question_id: UUID, body: QuestionChange
    ) -> QuestionView:
        with self.store.transaction(actor.user_id, offering_id) as tx:
            self._access(tx, teacher=True)
            record = next((q for q in tx.questions() if q.id == question_id), None)
            if record is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            if record.state != "open" or record.revision != body.expected_revision:
                raise ApiError(ErrorCode.CONFLICT)
            return self._question_view(
                tx.change_question(question_id, body.expected_revision, body.text, False), actor
            )

    def resolve_question(
        self, actor: ClassroomActor, offering_id: UUID, question_id: UUID, revision: int
    ) -> QuestionView:
        with self.store.transaction(actor.user_id, offering_id) as tx:
            self._access(tx, teacher=True)
            record = next((q for q in tx.questions() if q.id == question_id), None)
            if record is None:
                raise ApiError(ErrorCode.NOT_FOUND)
            if record.state != "answered" or record.revision != revision:
                raise ApiError(ErrorCode.CONFLICT)
            return self._question_view(tx.change_question(question_id, revision, None, True), actor)

    def submit_text(
        self, actor: ClassroomActor, offering_id: UUID, assignment_id: UUID, body: SubmissionInput
    ) -> SubmissionView:
        with self.store.transaction(actor.user_id, offering_id) as tx:
            self._access(tx)
            if tx.grant.role != "student":
                raise ApiError(ErrorCode.FORBIDDEN)
            assignment = next((a for a in tx.assignments() if a.id == assignment_id), None)
            if assignment is None or assignment.status == "draft":
                raise ApiError(ErrorCode.NOT_FOUND)
            now = self._now()
            if assignment.status != "published" or now >= assignment.deadline_at:
                raise ApiError(ErrorCode.CONFLICT)
            return tx.submit_text(
                assignment_id, actor.user_id, body.text, body.expected_revision, now
            )
