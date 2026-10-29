import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.features.campus import policy
from app.features.campus.domain import NoticeStatus
from app.features.notice_discussion.models import (
    Claim,
    Content,
    Item,
    ItemView,
    NoticeSummary,
    NoticeView,
    Page,
    QuestionInput,
)
from app.features.notice_discussion.ports import CurrentAccess, Store, UnitOfWork
from app.schemas.common import ErrorCode, utc_now

KEY_PATTERN = r"^[A-Za-z0-9-]{16,100}$"


def view(row: Item, actor_id: UUID) -> ItemView:
    return ItemView(
        **row.model_dump(exclude={"owner_id", "status"}), is_mine=row.owner_id == actor_id
    )


class NoticeDiscussionService:
    def __init__(self, store: Store, clock: Callable[[], datetime] = utc_now):
        self.store, self.clock = store, clock

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        return now

    @staticmethod
    def _access(
        uow: UnitOfWork, actor_id: UUID, department_id: UUID | None = None
    ) -> CurrentAccess:
        current = uow.current_access()
        if current is None or not current.active or current.actor.user_id != actor_id:
            raise ApiError(ErrorCode.UNAUTHORIZED)
        if not current.demo:
            raise ApiError(ErrorCode.FORBIDDEN)
        if department_id is not None and (
            department_id not in current.student_departments
            or not policy.belongs_to_department(current.actor, department_id)
        ):
            raise ApiError(ErrorCode.NOT_FOUND)
        return current

    @staticmethod
    def _page(offset: int, limit: int) -> None:
        if offset < 0 or not 1 <= limit <= 50:
            raise ApiError(ErrorCode.VALIDATION)

    def notices(self, actor_id: UUID, query: str = "", limit: int = 25) -> list[NoticeSummary]:
        self._page(0, limit)
        if len(query) > 100:
            raise ApiError(ErrorCode.VALIDATION)
        with self.store.unit_of_work(actor_id) as uow:
            access = self._access(uow, actor_id)
            rows = uow.notices.list_released_for(policy.actor_audiences(access.actor), limit)
            needle = query.strip().casefold()
            # Bounded filter of current authorized rows, not a complete school search index.
            return [
                NoticeSummary(id=n.id, title=n.title, status=n.status.value, revision=n.revision)
                for n in rows[:limit]
                if n.status is not NoticeStatus.DRAFT
                and policy.can_read_notice(access.actor, n)
                and needle in f"{n.title}\n{n.body}".casefold()
            ]

    def notice(self, actor_id: UUID, notice_id: UUID) -> NoticeView:
        with self.store.unit_of_work(actor_id) as uow:
            access = self._access(uow, actor_id)
            row = uow.notices.get(notice_id)
            if row is None or not policy.can_read_notice(access.actor, row):
                raise ApiError(ErrorCode.NOT_FOUND)
            return NoticeView(
                id=row.id,
                title=row.title,
                body=row.body,
                status=row.status.value,
                revision=row.revision,
                updated_at=row.updated_at,
                attachments=list(uow.notice_attachments(row.id, row.revision)),
                history=[
                    h
                    for h in uow.notice_history(row.id, row.revision)
                    if h.revision <= row.revision
                ],
            )

    @staticmethod
    def _item(uow: UnitOfWork, item_id: UUID, department_id: UUID, kind: str | None = None) -> Item:
        row = uow.get(item_id)
        if (
            row is None
            or row.department_id != department_id
            or row.status != "ACTIVE"
            or (kind is not None and row.kind != kind)
        ):
            raise ApiError(ErrorCode.NOT_FOUND)
        return row

    def items(
        self,
        actor_id: UUID,
        department_id: UUID,
        question_id: UUID | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> Page[ItemView]:
        self._page(offset, limit)
        with self.store.unit_of_work(actor_id) as uow:
            self._access(uow, actor_id, department_id)
            if question_id is not None:
                self._item(uow, question_id, department_id, "QUESTION")
                rows = uow.list_comments(question_id, offset, limit)
            else:
                rows = uow.list_questions(department_id, offset, limit)
            return Page(
                items=[
                    view(row, actor_id)
                    for row in rows[:limit]
                    if row.status == "ACTIVE"
                    and row.department_id == department_id
                    and row.question_id == question_id
                ],
                offset=offset,
                limit=limit,
            )

    def create(
        self,
        actor_id: UUID,
        department_id: UUID,
        body: QuestionInput | Content,
        key: str,
        question_id: UUID | None = None,
    ) -> ItemView:
        if re.fullmatch(KEY_PATTERN, key) is None:
            raise ApiError(ErrorCode.VALIDATION)
        if (question_id is None) != isinstance(body, QuestionInput):
            raise ApiError(ErrorCode.VALIDATION)
        with self.store.unit_of_work(actor_id) as uow:
            self._access(uow, actor_id, department_id)
            if question_id is not None:
                uow.lock_question(question_id)
                self._item(uow, question_id, department_id, "QUESTION")
            path = f"/departments/{department_id}/questions"
            if question_id is not None:
                path += f"/{question_id}/comments"
            digest = hashlib.sha256(
                json.dumps(body.model_dump(), sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            previous = uow.find_claim((actor_id, path, key))
            if previous is not None:
                if previous.namespace != (actor_id, path, key) or previous.digest != digest:
                    raise ApiError(ErrorCode.CONFLICT)
                row = uow.get(previous.item_id)
                if (
                    row is None
                    or row.status != "ACTIVE"
                    or row.owner_id != actor_id
                    or row.department_id != department_id
                    or row.question_id != question_id
                ):
                    raise ApiError(ErrorCode.CONFLICT)
                return view(row, actor_id)
            now = self._now()
            row = Item(
                id=uuid4(),
                department_id=department_id,
                owner_id=actor_id,
                kind="QUESTION" if question_id is None else "COMMENT",
                question_id=question_id,
                title=body.title if isinstance(body, QuestionInput) else None,
                body=body.body,
                record_source="DEMO",
                revision=1,
                created_at=now,
                updated_at=now,
            )
            uow.insert(
                row, Claim(actor_id=actor_id, path=path, key=key, digest=digest, item_id=row.id)
            )
            return view(row, actor_id)

    def change(
        self,
        actor_id: UUID,
        department_id: UUID,
        item_id: UUID,
        expected_revision: int,
        body: QuestionInput | Content | None,
    ) -> ItemView | None:
        if expected_revision < 1:
            raise ApiError(ErrorCode.VALIDATION)
        with self.store.unit_of_work(actor_id) as uow:
            self._access(uow, actor_id, department_id)
            row = self._item(uow, item_id, department_id)
            # Resolve parent, acquire the common lock, then re-read before deciding a write.
            uow.lock_question(row.question_id or row.id)
            row = self._item(uow, item_id, department_id)
            if row.question_id is not None:
                self._item(uow, row.question_id, department_id, "QUESTION")
            if row.owner_id != actor_id:
                raise ApiError(ErrorCode.NOT_FOUND)
            if row.revision != expected_revision:
                raise ApiError(ErrorCode.CONFLICT)
            if body is not None and (row.kind == "QUESTION") != isinstance(body, QuestionInput):
                raise ApiError(ErrorCode.VALIDATION)
            changes: dict[str, object] = {"revision": row.revision + 1, "updated_at": self._now()}
            if body is None:
                changes |= {"status": "DELETED", "body": "", "title": None}
            else:
                changes |= {"body": body.body}
                if isinstance(body, QuestionInput):
                    changes["title"] = body.title
            saved = row.model_copy(update=changes)
            uow.compare_and_set(saved, expected_revision)
            return None if body is None else view(saved, actor_id)
