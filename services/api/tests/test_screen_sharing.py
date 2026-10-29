"""Fictional in-process UOW only. Never remote DB, browser capture or real broker evidence."""

import copy
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import RLock
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ApiError
from app.factory import create_app
from app.features.classrooms.models import ClassroomActor, ClassroomGrant, Offering
from app.features.classrooms.router import get_classroom_actor
from app.features.screen_sharing.models import SignalInput, SignalRecord
from app.features.screen_sharing.router import get_screen_sharing_service, router
from app.features.screen_sharing.service import (
    MAX_CONTROL_WRITES,
    MAX_SIGNAL_BYTES,
    MAX_SIGNALS_PER_PEER,
    ScreenSharingService,
)
from app.schemas.common import ErrorCode

TEACHER, STUDENT, OTHER, COURSE, ELSEWHERE = (uuid4() for _ in range(5))
NOW = datetime(2026, 10, 30, tzinfo=UTC)
KEY = "fictional-operation-0001"
OFFER = "v=0\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\na=sendonly\r\n"
ANSWER = OFFER.replace("sendonly", "recvonly")


def actor(id=TEACHER):
    return ClassroomActor(user_id=id)


class FakeStore:
    def __init__(self):
        self.rows, self.member_rows, self.claims, self.messages = {}, {}, {}, {}
        self.lock = RLock()
        self.grants = {
            id: ClassroomGrant(active=True, role=role)
            for id, role in [(TEACHER, "teacher"), (STUDENT, "student"), (OTHER, "student")]
        }
        self.demo, self.fail = True, False
        self.control_counts = {}

    @contextmanager
    def transaction(self, user, offering):
        with self.lock:
            snapshot = copy.deepcopy(
                (self.rows, self.member_rows, self.claims, self.messages, self.control_counts)
            )
            store = self

            class Tx:
                actor_id = user
                active_demo_identity = store.demo
                classroom = SimpleNamespace(
                    grant=store.grants.get(user, ClassroomGrant(active=False, role="student")),
                    offering=Offering(
                        id=COURSE,
                        title="가상 분반",
                        term="가상 학기",
                        section="1",
                        instructor_name="가상 교수",
                    ),
                )

                def grant_for(self, id):
                    return store.grants.get(id)

                def current_session(self):
                    return next(reversed(store.rows.values()), None)

                def get_session(self, id):
                    return store.rows.get(id)

                def insert_session(self, row):
                    store.rows[row.id] = row

                def cas_session(self, row, revision):
                    if store.rows[row.id].revision != revision:
                        raise ApiError(ErrorCode.CONFLICT)
                    store.rows[row.id] = row

                def members(self, id):
                    return list(store.member_rows.get(id, {}).values())

                def put_member(self, id, member):
                    store.member_rows.setdefault(id, {})[member.user_id] = member

                def find_claim(self, actor, path, key):
                    return store.claims.get((actor, path, key))

                def insert_claim(self, claim):
                    namespace = claim.actor_id, claim.path, claim.key
                    if namespace in store.claims:
                        raise ApiError(ErrorCode.CONFLICT)
                    store.claims[namespace] = claim
                    if store.fail:
                        raise RuntimeError("fictional-private-signal-secret")

                def consume_control_budget(self, actor, now, maximum):
                    count = store.control_counts.get(actor, 0)
                    if count >= maximum:
                        raise ApiError(ErrorCode.RATE_LIMITED)
                    store.control_counts[actor] = count + 1

                def signal_count(self, id, peer):
                    return sum(s.sender_peer_id == peer for s in store.messages.get(id, []))

                def signal_bytes(self, id):
                    return getattr(
                        store,
                        "bytes_override",
                        sum(len(row.payload.encode("utf-8")) for row in store.messages.get(id, [])),
                    )

                def append_signal(self, id, sender, body):
                    row = SignalRecord(
                        sequence=len(store.messages.get(id, [])) + 1,
                        sender_peer_id=sender,
                        **body.model_dump(),
                    )
                    store.messages.setdefault(id, []).append(row)
                    return row

                def signals(self, id, recipient, generation, after, limit):
                    return [
                        s
                        for s in store.messages.get(id, [])
                        if s.target_peer_id == recipient
                        and s.target_generation == generation
                        and s.sequence > after
                    ][:limit]

            try:
                yield Tx()
            except BaseException:
                self.rows, self.member_rows, self.claims, self.messages, self.control_counts = (
                    snapshot
                )
                raise


@pytest.fixture
def context():
    store = FakeStore()
    return store, ScreenSharingService(store, clock=lambda: NOW)


def live(service):
    started = service.start(actor(), COURSE, KEY)
    session = service.state(actor(), COURSE, started.id, started.revision)
    student = service.join(actor(STUDENT), COURSE, session.id, KEY)
    return session, student


def signal(target, kind="OFFER", generation=1, target_generation=1):
    return SignalInput(
        target_peer_id=target,
        generation=generation,
        target_generation=target_generation,
        kind=kind,
        payload=OFFER if kind == "OFFER" else ANSWER if kind == "ANSWER" else "candidate:fictional",
    )


def test_teacher_only_single_presenter_start_replay_and_private_view(context):
    store, service = context
    with pytest.raises(ApiError):
        service.start(actor(STUDENT), COURSE, KEY)
    first = service.start(actor(), COURSE, KEY)
    assert service.start(actor(), COURSE, KEY).id == first.id
    with pytest.raises(ApiError) as error:
        service.start(actor(), COURSE, KEY + "new")
    assert error.value.code == ErrorCode.CONFLICT
    view = service.join(actor(STUDENT), COURSE, first.id, KEY)
    assert not view.is_presenter and view.viewers == [] and view.me.peer_id != STUDENT
    assert str(TEACHER) not in view.model_dump_json() and str(STUDENT) not in view.model_dump_json()
    assert view.audio is view.recording is False


def test_current_enrollment_identity_and_offering_scope_rechecked(context):
    store, service = context
    session, student = live(service)
    store.grants[STUDENT] = ClassroomGrant(active=False, role="student")
    with pytest.raises(ApiError):
        service.signals(actor(STUDENT), COURSE, session.id, 1, 0, 25)
    with pytest.raises(ApiError):
        service.join(actor(STUDENT), COURSE, session.id, KEY)
    with pytest.raises(ApiError):
        service.context(actor(), ELSEWHERE)
    store.demo = False
    with pytest.raises(ApiError) as error:
        service.context(actor(), COURSE)
    assert error.value.code == ErrorCode.UNAUTHORIZED


def test_targeted_signals_replay_payload_conflict_and_student_publishing_denied(context):
    store, service = context
    session, student = live(service)
    body = signal(student.me.peer_id)
    one = service.signal(actor(), COURSE, session.id, body, KEY)
    assert service.signal(actor(), COURSE, session.id, body, KEY) == one
    assert len(store.messages[session.id]) == 1
    assert service.signals(actor(), COURSE, session.id, 1, 0, 25).items == []
    page = service.signals(actor(STUDENT), COURSE, session.id, 1, 0, 25)
    assert len(page.items) == 1 and page.cursor == one
    with pytest.raises(ApiError):
        service.signal(actor(STUDENT), COURSE, session.id, signal(session.me.peer_id), KEY)
    with pytest.raises(ApiError):
        service.signal(actor(), COURSE, session.id, signal(student.me.peer_id, "ICE"), KEY)
    answer = signal(session.me.peer_id, "ANSWER")
    assert service.signal(actor(STUDENT), COURSE, session.id, answer, KEY)
    other = service.join(actor(OTHER), COURSE, session.id, KEY)
    with pytest.raises(ApiError):
        service.signal(
            actor(STUDENT), COURSE, session.id, signal(other.me.peer_id, "ICE"), KEY + "other"
        )


def test_recipient_revocation_blocks_delivery_replay_and_rejoin(context):
    store, service = context
    session, student = live(service)
    body = signal(student.me.peer_id)
    service.signal(actor(), COURSE, session.id, body, KEY)
    service.leave(actor(), COURSE, session.id, 1, student.me.peer_id)
    for operation in [
        lambda: service.signal(actor(), COURSE, session.id, body, KEY),
        lambda: service.join(actor(STUDENT), COURSE, session.id, KEY),
        lambda: service.signals(actor(STUDENT), COURSE, session.id, 1, 0, 25),
    ]:
        with pytest.raises(ApiError):
            operation()


def test_reconnect_generation_tombstones_old_signals_and_old_claim(context):
    store, service = context
    session, student = live(service)
    service.signal(actor(), COURSE, session.id, signal(student.me.peer_id), KEY)
    new = service.join(actor(STUDENT), COURSE, session.id, KEY + "reconnect", 1)
    assert new.me.generation == 2 and new.me.peer_id == student.me.peer_id
    assert service.signals(actor(STUDENT), COURSE, session.id, 2, 0, 25).items == []
    with pytest.raises(ApiError):
        service.signals(actor(STUDENT), COURSE, session.id, 1, 0, 25)
    with pytest.raises(ApiError):
        service.join(actor(STUDENT), COURSE, session.id, KEY)


def test_cas_end_and_expiry_never_resurrect_capture(context):
    store, service = context
    session, student = live(service)
    with pytest.raises(ApiError):
        service.state(actor(), COURSE, session.id, 1, True)
    ended = service.state(actor(), COURSE, session.id, 2, True)
    assert (
        ended.state == "ENDED" and service.state(actor(), COURSE, session.id, 2, True).revision == 3
    )
    with pytest.raises(ApiError):
        service.join(actor(STUDENT), COURSE, session.id, KEY + "new")
    service.clock = lambda: NOW + timedelta(minutes=16)
    assert service.context(actor(), COURSE).session is None
    with pytest.raises(ApiError):
        service.start(actor(), COURSE, KEY)


def test_claim_and_signal_budget_is_atomic_under_uow_contract(context):
    store, service = context
    store.fail = True
    with pytest.raises(RuntimeError):
        service.start(actor(), COURSE, KEY)
    assert not store.rows and not store.member_rows and not store.claims
    assert store.control_counts == {}
    store.fail = False
    session, student = live(service)
    body = signal(student.me.peer_id, "ICE")
    for i in range(MAX_SIGNALS_PER_PEER):
        service.signal(actor(), COURSE, session.id, body, f"fictional-candidate-{i:04}")
    with pytest.raises(ApiError) as error:
        service.signal(actor(), COURSE, session.id, body, KEY)
    assert error.value.code == ErrorCode.RATE_LIMITED


def test_shared_session_byte_budget_is_checked_before_append(context):
    store, service = context
    session, student = live(service)
    store.bytes_override = MAX_SIGNAL_BYTES
    with pytest.raises(ApiError) as error:
        service.signal(actor(), COURSE, session.id, signal(student.me.peer_id), KEY)
    assert error.value.code == ErrorCode.RATE_LIMITED
    assert store.messages == {}


def test_fresh_control_keys_are_bounded_but_valid_replay_does_not_consume_budget(context):
    store, service = context
    session, student = live(service)
    for index in range(MAX_CONTROL_WRITES - 1):
        service.join(actor(STUDENT), COURSE, session.id, f"fictional-new-key-{index:04}")
    assert store.control_counts[STUDENT] == MAX_CONTROL_WRITES
    before = len(store.claims)
    with pytest.raises(ApiError) as error:
        service.join(actor(STUDENT), COURSE, session.id, KEY + "overflow", 1)
    assert error.value.code == ErrorCode.RATE_LIMITED
    assert len(store.claims) == before
    assert service.join(actor(STUDENT), COURSE, session.id, KEY).me.generation == 1


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("OFFER", ANSWER),
        ("ANSWER", OFFER),
        ("OFFER", OFFER + "m=audio 9 RTP/AVP 0\r\n"),
        ("OFFER", OFFER.replace("sendonly", "sendrecv")),
        ("OFFER", "x" * 65537),
        ("ICE", "candidate:a\r\nprivate"),
        ("ICE", "candidate:" + "x" * 2048),
    ],
)
def test_audio_bidirectional_data_and_unbounded_signal_payload_rejected(kind, payload):
    with pytest.raises(ValidationError):
        SignalInput(
            target_peer_id=uuid4(), generation=1, target_generation=1, kind=kind, payload=payload
        )


def test_http_default_503_no_store_validation_safe_logs_and_unmounted(context, monkeypatch, caplog):
    application = create_app(Settings(environment="test"))
    assert not any("screen-sharing" in path for path in application.openapi()["paths"])
    application.include_router(router, prefix="/api/v1")
    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get(f"/api/v1/screen-sharing/{COURSE}")
        assert (
            response.status_code == 503 and response.headers["cache-control"] == "private, no-store"
        )
        application.dependency_overrides[get_classroom_actor] = actor
        application.dependency_overrides[get_screen_sharing_service] = lambda: context[1]
        response = client.post(
            f"/api/v1/screen-sharing/{COURSE}/sessions", headers={"Idempotency-Key": KEY}
        )
        assert response.status_code == 200 and "presenter_id" not in response.text
        bad = client.post(
            f"/api/v1/screen-sharing/{COURSE}/sessions", headers={"Idempotency-Key": "bad"}
        )
        assert bad.status_code == 400 and bad.headers["cache-control"] == "private, no-store"

        def fail(*args):
            raise RuntimeError("fictional-private-sdp-secret")

        monkeypatch.setattr(context[1], "context", fail)
        response = client.get(f"/api/v1/screen-sharing/{COURSE}")
        assert response.status_code == 500 and "private-sdp" not in caplog.text + response.text
