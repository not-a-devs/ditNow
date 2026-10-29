"""Persistence contracts for the community feature.

No production implementation exists in this branch: the platform DB (MariaDB) models and
migrations belong to the shared DB owner. Implementations MUST satisfy the notes below; the
in-memory fakes under ``tests/`` are test doubles only.
"""

from collections.abc import Iterable
from typing import Protocol

from app.features.community.domain import (
    AnonymousPostPrivate,
    AnonymousPostPublicRow,
    Recruitment,
)


class AnonymousPostRepository(Protocol):
    """``anonymous_posts_private`` ledger + ``anonymous_posts_public`` read model.

    - ``create``/``update`` write the private row and the public projection in ONE transaction;
      a projection failure must roll back the private write.
    - Public reads never join the private table and never return ``author_id``.
    - ``update`` is compare-and-set: persist only if the stored revision equals
      ``expected_revision``; return ``False`` otherwise.
    - Rows whose status is not ``active`` are removed from (or hidden in) the public model.
    """

    def create(self, post: AnonymousPostPrivate) -> None: ...

    def get_private(self, post_id: str) -> AnonymousPostPrivate | None: ...

    def update(self, post: AnonymousPostPrivate, expected_revision: int) -> bool: ...

    def get_public(self, post_id: str) -> AnonymousPostPublicRow | None: ...

    def list_public(self, *, limit: int, offset: int) -> list[AnonymousPostPublicRow]: ...

    def owned_post_ids(self, author_id: str, post_ids: Iterable[str]) -> set[str]:
        """Server-side ``is_mine`` lookup; the result is reduced to a boolean per post."""
        ...


class RecruitmentRepository(Protocol):
    """``recruitments`` ledger. ``update`` is compare-and-set on ``revision``.

    FR-COM-005 acceptance (P1, not exposed here) must lock the recruitment row, re-check
    deadline/status and ``1 + accepted_count < capacity`` inside the same transaction.
    """

    def create(self, recruitment: Recruitment) -> None: ...

    def get(self, recruitment_id: str) -> Recruitment | None: ...

    def update(self, recruitment: Recruitment, expected_revision: int) -> bool: ...

    def list(self, *, limit: int, offset: int) -> list[Recruitment]: ...


class PublicProfileReader(Protocol):
    """Batch read of allowed real-name activity profile fields (avoids N+1 per NFR-REL-005)."""

    def display_names(self, user_ids: Iterable[str]) -> dict[str, str]: ...
