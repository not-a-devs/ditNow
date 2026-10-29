import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.features.classrooms.models import ClassroomActor
from app.features.screen_sharing.models import (
    Claim,
    ContextView,
    Member,
    PeerView,
    SessionRecord,
    SessionView,
    SignalInput,
    SignalPage,
    SignalView,
)
from app.features.screen_sharing.ports import Store, Transaction
from app.schemas.common import ErrorCode, utc_now

KEY_PATTERN = r"^[A-Za-z0-9-]{16,100}$"
# Bounded demo design defaults; not institutional retention/capacity/performance promises.
SESSION_LIFETIME = timedelta(minutes=15)
MAX_MEMBERS = 50
MAX_SIGNALS_PER_PEER = 256
MAX_SIGNAL_BYTES = 4 * 1024 * 1024
MAX_CONTROL_WRITES = 32


class ScreenSharingService:
    def __init__(self, store: Store, clock: Callable[[], datetime] = utc_now):
        self.store, self.clock = store, clock

    def _now(self):
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ApiError(ErrorCode.UNAVAILABLE)
        return now.astimezone(UTC)

    @staticmethod
    def _access(tx: Transaction, actor: ClassroomActor, offering: UUID, teacher=False):
        if tx.actor_id != actor.user_id or not tx.active_demo_identity:
            raise ApiError(ErrorCode.UNAUTHORIZED)
        if tx.classroom.offering.id != offering:
            raise ApiError(ErrorCode.NOT_FOUND)
        grant = tx.classroom.grant
        if not grant.active or (teacher and grant.role != "teacher"):
            raise ApiError(ErrorCode.FORBIDDEN)

    def _session(self, tx: Transaction, id: UUID, offering: UUID, ended=False):
        row = tx.get_session(id)
        if row is None or row.offering_id != offering:
            raise ApiError(ErrorCode.NOT_FOUND)
        if row.expires_at <= self._now() or (not ended and row.state == "ENDED"):
            raise ApiError(ErrorCode.CONFLICT)
        return row

    @staticmethod
    def _members(tx: Transaction, session: SessionRecord):
        members = list(tx.members(session.id))
        if len(members) > MAX_MEMBERS or len({m.user_id for m in members}) != len(members):
            raise ApiError(ErrorCode.UNAVAILABLE)
        return members

    @staticmethod
    def _permitted(tx: Transaction, session: SessionRecord, member: Member):
        grant = tx.grant_for(member.user_id)
        return (
            member.status == "ACTIVE"
            and grant is not None
            and grant.active
            and (member.user_id != session.presenter_id or grant.role == "teacher")
        )

    def _member(self, tx: Transaction, session: SessionRecord, user: UUID):
        member = next((m for m in self._members(tx, session) if m.user_id == user), None)
        if member is None or not self._permitted(tx, session, member):
            raise ApiError(ErrorCode.FORBIDDEN)
        return member

    def _view(self, tx: Transaction, session: SessionRecord, user: UUID):
        members = self._members(tx, session)
        active = [m for m in members if self._permitted(tx, session, m)]
        me = next((m for m in active if m.user_id == user), None)
        presenter = next((m for m in active if m.user_id == session.presenter_id), None)
        owner = session.presenter_id == user
        return SessionView(
            **session.model_dump(exclude={"presenter_id", "created_at"}),
            is_presenter=owner,
            me=PeerView(peer_id=me.peer_id, generation=me.generation) if me else None,
            presenter=PeerView(peer_id=presenter.peer_id, generation=presenter.generation)
            if presenter
            else None,
            viewers=[
                PeerView(peer_id=m.peer_id, generation=m.generation)
                for m in active
                if m.user_id != user
            ]
            if owner
            else [],
        )

    @staticmethod
    def _claim(tx: Transaction, actor: UUID, path: str, key: str, body: dict):
        if re.fullmatch(KEY_PATTERN, key) is None:
            raise ApiError(ErrorCode.VALIDATION)
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        previous = tx.find_claim(actor, path, key)
        if previous and (
            (previous.actor_id, previous.path, previous.key) != (actor, path, key)
            or previous.digest != digest
        ):
            raise ApiError(ErrorCode.CONFLICT)
        return previous, digest

    def context(self, actor: ClassroomActor, offering: UUID):
        with self.store.transaction(actor.user_id, offering) as tx:
            self._access(tx, actor, offering)
            session = tx.current_session()
            if session is not None and session.offering_id != offering:
                raise ApiError(ErrorCode.UNAVAILABLE)
            if session and session.expires_at <= self._now():
                session = None
            return ContextView(
                offering_id=offering,
                role=tx.classroom.grant.role,
                session=self._view(tx, session, actor.user_id) if session else None,
            )

    def start(self, actor: ClassroomActor, offering: UUID, key: str):
        with self.store.transaction(actor.user_id, offering) as tx:
            self._access(tx, actor, offering, teacher=True)
            path = f"/{offering}/sessions"
            previous, digest = self._claim(tx, actor.user_id, path, key, {})
            if previous:
                session = self._session(tx, previous.result_id, offering, ended=True)
                if session.presenter_id != actor.user_id:
                    raise ApiError(ErrorCode.CONFLICT)
                return self._view(tx, session, actor.user_id)
            current = tx.current_session()
            if current and current.state != "ENDED" and current.expires_at > self._now():
                raise ApiError(ErrorCode.CONFLICT)
            now = self._now()
            tx.consume_control_budget(actor.user_id, now, MAX_CONTROL_WRITES)
            session = SessionRecord(
                id=uuid4(),
                offering_id=offering,
                presenter_id=actor.user_id,
                revision=1,
                created_at=now,
                expires_at=now + SESSION_LIFETIME,
            )
            tx.insert_session(session)
            tx.put_member(session.id, Member(peer_id=uuid4(), user_id=actor.user_id, generation=1))
            tx.insert_claim(
                Claim(
                    actor_id=actor.user_id, path=path, key=key, digest=digest, result_id=session.id
                )
            )
            return self._view(tx, session, actor.user_id)

    def state(self, actor: ClassroomActor, offering: UUID, id: UUID, revision: int, end=False):
        with self.store.transaction(actor.user_id, offering) as tx:
            self._access(tx, actor, offering, teacher=True)
            session = self._session(tx, id, offering, ended=end)
            if session.presenter_id != actor.user_id:
                raise ApiError(ErrorCode.FORBIDDEN)
            self._member(tx, session, actor.user_id)
            if session.state == "ENDED" and end:
                return self._view(tx, session, actor.user_id)
            if (
                revision < 1
                or session.revision != revision
                or (not end and session.state != "READY")
            ):
                raise ApiError(ErrorCode.CONFLICT)
            updated = session.model_copy(
                update={"state": "ENDED" if end else "LIVE", "revision": revision + 1}
            )
            tx.cas_session(updated, revision)
            return self._view(tx, updated, actor.user_id)

    def join(
        self, actor: ClassroomActor, offering: UUID, id: UUID, key: str, expected: int | None = None
    ):
        with self.store.transaction(actor.user_id, offering) as tx:
            self._access(tx, actor, offering)
            session = self._session(tx, id, offering)
            members = self._members(tx, session)
            me = next((m for m in members if m.user_id == actor.user_id), None)
            if me and me.status == "REVOKED":
                raise ApiError(ErrorCode.FORBIDDEN)
            path = f"/{offering}/sessions/{id}/{'join' if expected is None else 'reconnect'}"
            previous, digest = self._claim(tx, actor.user_id, path, key, {"expected": expected})
            if previous:
                if (
                    not me
                    or not self._permitted(tx, session, me)
                    or me.generation != previous.result_generation
                ):
                    raise ApiError(ErrorCode.CONFLICT)
                return self._view(tx, session, actor.user_id)
            if expected is not None and (
                not me or me.generation != expected or me.status != "ACTIVE"
            ):
                raise ApiError(ErrorCode.CONFLICT)
            if me is None and len(members) >= MAX_MEMBERS:
                raise ApiError(ErrorCode.RATE_LIMITED)
            tx.consume_control_budget(actor.user_id, self._now(), MAX_CONTROL_WRITES)
            if expected is None and me and me.status == "ACTIVE":
                updated = me
            else:
                updated = Member(
                    peer_id=me.peer_id if me else uuid4(),
                    user_id=actor.user_id,
                    generation=me.generation + 1 if me else 1,
                )
                tx.put_member(session.id, updated)
            tx.insert_claim(
                Claim(
                    actor_id=actor.user_id,
                    path=path,
                    key=key,
                    digest=digest,
                    result_id=updated.peer_id,
                    result_generation=updated.generation,
                )
            )
            return self._view(tx, session, actor.user_id)

    def leave(
        self,
        actor: ClassroomActor,
        offering: UUID,
        id: UUID,
        generation: int,
        revoke: UUID | None = None,
    ):
        with self.store.transaction(actor.user_id, offering) as tx:
            self._access(tx, actor, offering, teacher=revoke is not None)
            session = self._session(tx, id, offering)
            me = self._member(tx, session, actor.user_id)
            if me.generation != generation:
                raise ApiError(ErrorCode.CONFLICT)
            if revoke is not None:
                if session.presenter_id != actor.user_id or revoke == me.peer_id:
                    raise ApiError(ErrorCode.FORBIDDEN)
                target = next((m for m in self._members(tx, session) if m.peer_id == revoke), None)
                if target is None:
                    raise ApiError(ErrorCode.NOT_FOUND)
            else:
                target = me
                if session.presenter_id == actor.user_id:
                    raise ApiError(
                        ErrorCode.CONFLICT
                    )  # Presenter must end the session, not orphan it.
            tx.put_member(
                session.id, target.model_copy(update={"status": "REVOKED" if revoke else "LEFT"})
            )

    def signal(self, actor: ClassroomActor, offering: UUID, id: UUID, body: SignalInput, key: str):
        with self.store.transaction(actor.user_id, offering) as tx:
            self._access(tx, actor, offering)
            session = self._session(tx, id, offering)
            if session.state != "LIVE":
                raise ApiError(ErrorCode.CONFLICT)
            me = self._member(tx, session, actor.user_id)
            target = next(
                (m for m in self._members(tx, session) if m.peer_id == body.target_peer_id), None
            )
            if target is None or not self._permitted(tx, session, target):
                raise ApiError(ErrorCode.NOT_FOUND)
            if me.generation != body.generation or target.generation != body.target_generation:
                raise ApiError(ErrorCode.CONFLICT)
            presenter = session.presenter_id
            if me.peer_id == target.peer_id or (
                me.user_id != presenter and target.user_id != presenter
            ):
                raise ApiError(ErrorCode.FORBIDDEN)
            if (body.kind == "OFFER" and me.user_id != presenter) or (
                body.kind == "ANSWER" and me.user_id == presenter
            ):
                raise ApiError(ErrorCode.FORBIDDEN)
            path = f"/{offering}/sessions/{id}/signals"
            previous, digest = self._claim(
                tx, actor.user_id, path, key, body.model_dump(mode="json")
            )
            if previous:
                return previous.sequence
            if (
                tx.signal_count(id, me.peer_id) >= MAX_SIGNALS_PER_PEER
                or tx.signal_bytes(id) + len(body.payload.encode("utf-8")) > MAX_SIGNAL_BYTES
            ):
                raise ApiError(ErrorCode.RATE_LIMITED)
            saved = tx.append_signal(id, me.peer_id, body)
            tx.insert_claim(
                Claim(
                    actor_id=actor.user_id,
                    path=path,
                    key=key,
                    digest=digest,
                    result_id=me.peer_id,
                    result_generation=me.generation,
                    sequence=saved.sequence,
                )
            )
            return saved.sequence

    def signals(
        self,
        actor: ClassroomActor,
        offering: UUID,
        id: UUID,
        generation: int,
        after: int,
        limit: int,
    ):
        if after < 0 or not 1 <= limit <= 50:
            raise ApiError(ErrorCode.VALIDATION)
        with self.store.transaction(actor.user_id, offering) as tx:
            self._access(tx, actor, offering)
            session = self._session(tx, id, offering)
            me = self._member(tx, session, actor.user_id)
            if me.generation != generation:
                raise ApiError(ErrorCode.CONFLICT)
            rows = list(tx.signals(id, me.peer_id, generation, after, limit))[:limit]
            members = {m.peer_id: m for m in self._members(tx, session)}
            result = []
            cursor = after
            for row in rows:
                if (
                    row.sequence <= cursor
                    or row.target_peer_id != me.peer_id
                    or row.target_generation != generation
                ):
                    raise ApiError(ErrorCode.UNAVAILABLE)
                cursor = row.sequence
                sender = members.get(row.sender_peer_id)
                if (
                    sender
                    and sender.generation == row.generation
                    and self._permitted(tx, session, sender)
                ):
                    result.append(
                        SignalView(
                            **row.model_dump(exclude={"target_peer_id", "target_generation"})
                        )
                    )
            return SignalPage(items=result, cursor=cursor)
