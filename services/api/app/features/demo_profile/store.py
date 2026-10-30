"""Explicit in-process demo store. Contents vanish on restart; this is NOT MariaDB persistence.

Unwritten owners read the fixed synthetic default without consuming capacity. Only the first
successful PATCH allocates an owner slot, bounded by ``max_owners``.
"""

from dataclasses import dataclass
from threading import Lock
from uuid import UUID

from app.core.errors import ApiError
from app.features.demo_profile.schemas import (
    DemoInterest,
    DemoProfilePreferences,
    DemoProfileUpdate,
    SkillLevel,
)
from app.schemas.common import ErrorCode

MAX_OWNERS = 200


@dataclass(frozen=True)
class _Entry:
    interests: tuple[DemoInterest, ...]
    skill_level: SkillLevel
    revision: int

    def public(self) -> DemoProfilePreferences:
        return DemoProfilePreferences(
            interests=list(self.interests), skill_level=self.skill_level, revision=self.revision
        )


_DEFAULT = _Entry(interests=(), skill_level=SkillLevel.BEGINNER, revision=1)


class DemoProfileStore:
    def __init__(self, *, max_owners: int = MAX_OWNERS) -> None:
        if not 1 <= max_owners <= MAX_OWNERS:
            raise ValueError("max_owners must be between 1 and 200")
        self._max_owners = max_owners
        self._entries: dict[UUID, _Entry] = {}
        self._lock = Lock()

    def get(self, owner: UUID) -> DemoProfilePreferences:
        with self._lock:
            return self._entries.get(owner, _DEFAULT).public()

    def update(self, owner: UUID, payload: DemoProfileUpdate) -> DemoProfilePreferences:
        with self._lock:
            current = self._entries.get(owner)
            if (current or _DEFAULT).revision != payload.revision:
                raise ApiError(ErrorCode.CONFLICT)
            if current is None and len(self._entries) >= self._max_owners:
                raise ApiError(ErrorCode.UNAVAILABLE)
            entry = _Entry(
                interests=tuple(payload.interests),
                skill_level=payload.skill_level,
                revision=payload.revision + 1,
            )
            self._entries[owner] = entry
            return entry.public()

    def owner_count(self) -> int:
        with self._lock:
            return len(self._entries)
