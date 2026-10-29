from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.features.classrooms.models import (
    Assignment,
    ClassroomGrant,
    Material,
    Offering,
    QuestionRecord,
    SubmissionView,
)


class ClassroomTransaction(Protocol):
    """An adapter must revalidate active enrollment/teacher assignment in this transaction.

    All reads/writes are offering-scoped. Mutations must serialize/CAS revisions and persist
    idempotency keys with their payload. Keys are namespaced by actor + offering + method/path;
    compare a canonical payload hash, and same key/different payload is CONFLICT. Replays still
    revalidate current permission and must not bypass revocation or disclose another actor's row.
    Revocation,
    deadline/state changes and the write must be covered by the same transaction/locking.
    No implementation or in-memory runtime fallback is installed by this feature.
    """

    grant: ClassroomGrant
    offering: Offering

    def materials(self) -> list[Material]: ...

    def assignments(self) -> list[Assignment]: ...

    def questions(self) -> list[QuestionRecord]: ...

    def my_submissions(self, author_id: UUID) -> list[SubmissionView]: ...

    def create_question(
        self, author_id: UUID, text: str, idempotency_key: str, now: datetime
    ) -> QuestionRecord: ...

    def change_question(
        self, question_id: UUID, expected_revision: int, answer: str | None, resolve: bool
    ) -> QuestionRecord: ...

    def submit_text(
        self, assignment_id: UUID, author_id: UUID, text: str, expected_revision: int, now: datetime
    ) -> SubmissionView: ...


class ClassroomStore(Protocol):
    def my_offering_ids(self, user_id: UUID, limit: int) -> list[UUID]:
        """Only current authorized offerings, bounded by limit; never a public catalog."""
        ...

    def transaction(
        self, user_id: UUID, offering_id: UUID
    ) -> AbstractContextManager[ClassroomTransaction]: ...
