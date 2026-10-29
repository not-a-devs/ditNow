from contextlib import AbstractContextManager
from typing import Protocol
from uuid import UUID

from .models import ActivityProfileRecord, CurrentProfileAccess, ProfileEditPolicy


class ProfileConflict(Exception):
    """CAS or same-key/different-body conflict after full transaction rollback."""


class ProfileTransaction(Protocol):
    """One current actor-bound UOW, not an implemented MariaDB repository.

    Lock current identity/membership, edit policy and existing activity profile in that order.
    All reads after waits must see current committed grants/policy/rows. Revocation must
    serialize with the same locks. No alias/user/role provisioning or public-profile sync.
    self_profile MUST select by the server actor, never a request user ID. Missing rows stay
    missing. Map existing interest_tags/interests under the single profile source of truth;
    do not create a competing profile/identity table.

    UNIQUE(actor,operation='self-profile-update',key), exact-case key and canonical body hash.
    Replay conflicts roll back; retain replay/tombstones and never recreate removed rows.
    save updates ONLY skills/interests/bio and their revision/time under actor+CAS. It must
    preserve display_name/department/year/roles/status. Activity row, replay receipt and a
    minimal change event (not old/new bio or tags) commit/rollback atomically.
    """

    access: CurrentProfileAccess
    policy: ProfileEditPolicy | None

    def self_profile(self) -> ActivityProfileRecord | None: ...
    def replay(self, key: str, body_hash: str) -> bool: ...
    def save(
        self, row: ActivityProfileRecord, expected_revision: int, key: str, body_hash: str
    ) -> ActivityProfileRecord: ...


class ProfileStore(Protocol):
    def transaction(self, actor_id: UUID) -> AbstractContextManager[ProfileTransaction]: ...
