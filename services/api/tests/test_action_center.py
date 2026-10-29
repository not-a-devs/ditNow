"""Test-only fake contracts: never runtime storage, login seed or proof of MariaDB behaviour."""

import copy
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from threading import RLock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.action_center.models import NotificationEvent, SourceType
from app.features.action_center.ports import SourceRef
from app.features.action_center.router import get_actor, get_service, router
from app.features.action_center.service import ActionCenterService
from app.features.campus.domain import (
    Audience,
    AudienceType,
    CampusActor,
    Membership,
    Notice,
    NoticeStatus,
)
from app.features.notice_discussion.ports import CurrentAccess
from app.schemas.common import ErrorCode

# 23:30 at +09:00; the display day starts at 2026-10-29T15:00Z, not at UTC midnight.
NOW = datetime(2026, 10, 30, 14, 30, tzinfo=UTC)
ACTOR, OTHER, DEPT, ELSEWHERE, NOTICE, HIDDEN = (uuid4() for _ in range(6))
CLASS, TASK, DEADLINE, LATE_CLASS = (uuid4() for _ in range(4))


def notice(id, audience, status=NoticeStatus.PUBLISHED, at=NOW):
    return Notice(id, audience, "가상 공지", "본문", status, 1, OTHER, at, at, at)


class FakeStore:
    def __init__(self):
        self.lock = RLock()
        self.rows = {}
        self.access = {
            a: CurrentAccess(CampusActor(a, (Membership(DEPT, 2),)), True, True, frozenset({DEPT}))
            for a in (ACTOR, OTHER)
        }
        self.notices = {
            NOTICE: notice(NOTICE, Audience(AudienceType.DEPARTMENT, DEPT)),
            HIDDEN: notice(HIDDEN, Audience(AudienceType.DEPARTMENT, ELSEWHERE)),
        }
        self.visible = {ACTOR: {CLASS, TASK, DEADLINE}, OTHER: set()}
        start = datetime(2026, 10, 30, tzinfo=timezone(timedelta(hours=9)))
        self.refs = {
            SourceType.CLASS_SESSION: [
                SourceRef(SourceType.CLASS_SESSION, CLASS, "가상 자료구조", start, "DEMO"),
                SourceRef(
                    SourceType.CLASS_SESSION, LATE_CLASS, "내일 수업", start + timedelta(1), "DEMO"
                ),
            ],
            SourceType.TASK: [SourceRef(SourceType.TASK, TASK, "가상 과제", NOW, "DEMO")],
            SourceType.OPPORTUNITY_DEADLINE: [
                SourceRef(
                    SourceType.OPPORTUNITY_DEADLINE,
                    DEADLINE,
                    "공개 장학 마감",
                    NOW + timedelta(days=3),
                    "OFFICIAL_PUBLIC",
                )
            ],
        }
        self.calls = []
        self.fail_insert = False

    @contextmanager
    def unit_of_work(self, actor):
        with self.lock:
            before = copy.deepcopy(self.rows)
            store = self

            class Notices:
                def get(self, id):
                    return store.notices.get(id)

                def get_many(self, ids):
                    return {i: store.notices[i] for i in ids if i in store.notices}

                def list_released_for(self, audiences, limit):
                    return [n for n in store.notices.values() if n.audience in audiences][:limit]

            class Sources:
                def _list(self, kind, start, end, limit):
                    store.calls.append((kind, start, end, limit))
                    return [r for r in store.refs[kind] if r.source_id in store.visible[actor]]

                def classes_between(self, start, end, limit):
                    return self._list(SourceType.CLASS_SESSION, start, end, limit)

                def tasks_due_between(self, start, end, limit):
                    return self._list(SourceType.TASK, start, end, limit)

                def deadlines_between(self, start, end, limit):
                    return self._list(SourceType.OPPORTUNITY_DEADLINE, start, end, limit)

                def is_visible(self, kind, id):
                    return id in store.visible[actor]

            class Uow:
                notices = Notices()
                sources = Sources()

                def current_access(self):
                    return store.access.get(actor)

                def _mine(self):
                    rows = [r for r in store.rows.values() if r.recipient_id == actor]
                    return sorted(rows, key=lambda r: (r.created_at, str(r.id)), reverse=True)

                def list_notifications(self, offset, limit):
                    return self._mine()[offset : offset + limit]

                def list_unread(self, limit):
                    return [r for r in self._mine() if r.read_at is None][:limit]

                def get_notification(self, id):
                    row = store.rows.get(id)
                    return row if row and row.recipient_id == actor else None

                def find_notification(self, key):
                    return next((r for r in store.rows.values() if r.dedupe_key == key), None)

                def insert_notification(self, row):
                    if self.find_notification(row.dedupe_key):
                        raise ApiError(ErrorCode.CONFLICT)
                    store.rows[row.id] = row
                    if store.fail_insert:
                        raise RuntimeError("fictional-storage-failure")

                def mark_read(self, row, expected):
                    current = store.rows.get(row.id)
                    if (
                        current is None
                        or current.recipient_id != actor
                        or current.revision != expected
                        or current.read_at is not None
                    ):
                        return False
                    store.rows[row.id] = row
                    return True

            try:
                yield Uow()
            except BaseException:
                store.rows = before
                raise


@pytest.fixture
def context():
    store = FakeStore()
    return store, ActionCenterService(store, clock=lambda: NOW)


def event(
    kind=SourceType.NOTICE, source=NOTICE, key="notice.published:r1", label="PLATFORM", to=ACTOR
):
    return NotificationEvent(
        recipient_id=to,
        source_type=kind,
        source_id=source,
        event_key=key,
        title="가상 공지 알림",
        record_source=label,
    )


def test_summary_aggregates_current_references_in_bounded_windows(context):
    store, service = context
    result = service.summary(ACTOR)
    assert str(result.local_date) == "2026-10-30" and result.utc_offset == "+09:00"
    assert result.window_start == datetime(2026, 10, 29, 15, tzinfo=UTC)
    assert [i.source_id for i in result.classes] == [CLASS]  # tomorrow's class is outside today
    assert [i.source_id for i in result.tasks] == [TASK]
    assert result.deadlines[0].record_source == "OFFICIAL_PUBLIC"
    assert [i.source_id for i in result.notices] == [NOTICE]  # other department filtered
    assert result.notices[0].record_source == "PLATFORM"
    assert {i.link for i in result.classes + result.notices} == {
        "/app/classrooms",
        "/app/department",
    }
    assert result.priority_policy == "NOT_DEFINED" and result.school_connection == "NOT_CONNECTED"
    assert all(limit == 10 for *_, limit in store.calls)
    assert all(start.tzinfo is not None for _, start, _, _ in store.calls)


def test_summary_is_per_current_actor_and_reflects_membership_revocation(context):
    store, service = context
    other = service.summary(OTHER)
    assert other.classes == [] and other.tasks == [] and other.deadlines == []
    store.access[ACTOR] = CurrentAccess(CampusActor(ACTOR, ()), True, True, frozenset())
    assert service.summary(ACTOR).notices == []


@pytest.mark.parametrize(
    "access,code",
    [
        (None, ErrorCode.UNAUTHORIZED),
        (CurrentAccess(CampusActor(ACTOR), False, True, frozenset()), ErrorCode.UNAUTHORIZED),
        (CurrentAccess(CampusActor(OTHER), True, True, frozenset()), ErrorCode.UNAUTHORIZED),
        (CurrentAccess(CampusActor(ACTOR), True, False, frozenset()), ErrorCode.FORBIDDEN),
    ],
)
def test_current_server_access_is_required(context, access, code):
    store, service = context
    store.access[ACTOR] = access
    for call in (lambda: service.summary(ACTOR), lambda: service.inbox(ACTOR)):
        with pytest.raises(ApiError) as error:
            call()
        assert error.value.code is code


def test_provider_contract_violation_and_naive_clock_fail_closed(context):
    store, service = context
    store.refs[SourceType.TASK] = [SourceRef(SourceType.NOTICE, TASK, "섞인 원본", NOW, "DEMO")]
    with pytest.raises(ApiError) as error:
        service.summary(ACTOR)
    assert error.value.code is ErrorCode.UNAVAILABLE
    naive = ActionCenterService(store, clock=lambda: datetime(2026, 10, 30))
    with pytest.raises(ApiError) as error:
        naive.summary(ACTOR)
    assert error.value.code is ErrorCode.UNAVAILABLE


def test_delivery_is_idempotent_on_duplicate_source_event(context):
    store, service = context
    first = service.deliver(event())
    again = service.deliver(event())
    assert first is not None and again is not None and first.id == again.id
    assert len(store.rows) == 1
    revised = service.deliver(event(key="notice.revised:r2"))
    assert revised is not None and revised.id != first.id and len(store.rows) == 2
    assert service.summary(ACTOR).unread_notifications == 2


def test_delivery_and_replay_respect_current_visibility(context):
    store, service = context
    assert service.deliver(event(source=HIDDEN)) is None  # recipient outside the audience
    assert service.deliver(event(to=OTHER, kind=SourceType.TASK, source=TASK, label="DEMO")) is None
    task = service.deliver(
        event(kind=SourceType.TASK, source=TASK, key="task.due:d1", label="DEMO")
    )
    assert task is not None
    store.visible[ACTOR].discard(TASK)  # enrollment dropped
    assert (
        service.deliver(event(kind=SourceType.TASK, source=TASK, key="task.due:d1", label="DEMO"))
        is None
    )
    assert service.inbox(ACTOR).items == [] and service.summary(ACTOR).unread_notifications == 0
    with pytest.raises(ApiError) as error:
        service.mark_read(ACTOR, task.id, 1)
    assert error.value.code is ErrorCode.NOT_FOUND
    store.access[ACTOR] = CurrentAccess(CampusActor(ACTOR), False, True, frozenset())
    assert service.deliver(event(key="notice.published:r9")) is None


def test_delivery_label_must_match_source_and_rolls_back_on_failure(context):
    store, service = context
    with pytest.raises(ApiError):
        service.deliver(event(label="DEMO"))
    with pytest.raises(ValidationError):
        event(key="bad key with spaces")
    store.fail_insert = True
    with pytest.raises(RuntimeError):
        service.deliver(event())
    assert store.rows == {}


def test_mark_read_cas_replay_and_other_recipient(context):
    store, service = context
    row = service.deliver(event())
    assert row is not None
    with pytest.raises(ApiError) as error:
        service.mark_read(ACTOR, row.id, 7)
    assert error.value.code is ErrorCode.CONFLICT
    done = service.mark_read(ACTOR, row.id, 1)
    assert done.read_at == NOW and done.revision == 2
    assert service.mark_read(ACTOR, row.id, 1).revision == 2  # replay is a no-op
    assert store.rows[row.id].revision == 2
    with pytest.raises(ApiError) as error:
        service.mark_read(OTHER, row.id, 2)
    assert error.value.code is ErrorCode.NOT_FOUND
    assert service.summary(ACTOR).unread_notifications == 0


def test_concurrent_cas_loser_gets_conflict(context):
    store, service = context
    row = service.deliver(event())
    original = store.rows[row.id]
    store.rows[row.id] = original.model_copy(update={"revision": 2})  # another writer won
    with pytest.raises(ApiError) as error:
        service.mark_read(ACTOR, row.id, 1)
    assert error.value.code is ErrorCode.CONFLICT


def test_inbox_pagination_advances_past_hidden_rows(context):
    store, service = context
    service.deliver(event())
    service.deliver(event(kind=SourceType.TASK, source=TASK, key="task.due:d1", label="DEMO"))
    store.visible[ACTOR].discard(TASK)
    page = service.inbox(ACTOR, 0, 2)
    assert len(page.items) == 1 and page.next_offset == 2
    with pytest.raises(ApiError):
        service.inbox(ACTOR, -1, 2)


def app(context=None):
    application = create_app(Settings(environment="test"))
    application.include_router(router, prefix="/api/v1")
    if context is not None:
        application.dependency_overrides[get_actor] = lambda: ACTOR
        application.dependency_overrides[get_service] = lambda: context[1]
    return application


def test_default_dependencies_fail_closed_and_routes_not_global():
    with TestClient(app()) as client:
        for response in (
            client.get("/api/v1/action-center/summary"),
            client.post(
                f"/api/v1/action-center/notifications/{uuid4()}/read", json={"expected_revision": 1}
            ),
        ):
            assert response.status_code == 503
            assert response.headers["cache-control"] == "private, no-store"
    paths = create_app(Settings(environment="test")).openapi()["paths"]
    assert not any("action-center" in p for p in paths)


def test_http_contract_private_and_no_recipient_or_actor_param(context):
    store, service = context
    row = service.deliver(event())
    with TestClient(app(context)) as client:
        summary = client.get("/api/v1/action-center/summary", params={"actor_id": str(OTHER)})
        assert summary.status_code == 200
        assert summary.headers["cache-control"] == "private, no-store"
        assert summary.json()["data"]["unread_notifications"] == 1
        inbox = client.get("/api/v1/action-center/notifications")
        assert str(ACTOR) not in inbox.text and "event_key" not in inbox.text
        assert inbox.json()["data"]["items"][0]["delivery"] == "IN_APP_ONLY"
        bad = client.post(
            f"/api/v1/action-center/notifications/{row.id}/read",
            json={"expected_revision": 1, "recipient_id": str(OTHER)},
        )
        assert bad.status_code == 400 and bad.headers["cache-control"] == "private, no-store"
        ok = client.post(
            f"/api/v1/action-center/notifications/{row.id}/read", json={"expected_revision": 1}
        )
        assert ok.status_code == 200 and ok.json()["data"]["revision"] == 2
        assert client.get("/api/v1/action-center/notifications?limit=51").status_code == 400


def test_unexpected_storage_error_is_generic(context, monkeypatch, caplog):
    def fail(*args):
        raise RuntimeError("fictional-secret-title")

    monkeypatch.setattr(context[1], "summary", fail)
    with TestClient(app(context), raise_server_exceptions=False) as client:
        response = client.get("/api/v1/action-center/summary")
        assert response.status_code == 500
        assert response.headers["cache-control"] == "private, no-store"
        assert "fictional-secret" not in response.text and "fictional-secret" not in caplog.text
