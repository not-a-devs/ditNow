"""Unit tests for idempotent community creates at the service/Protocol boundary.

The repositories below are TEST-ONLY doubles that model the atomic claim contract (including a
lost race); no database is involved.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import ApiError
from app.features.community import AnonymousPostService, CommunityActor, RecruitmentService
from app.features.community.idempotency import IdempotencyClaim, body_digest, new_claim
from app.features.community.schemas import AnonymousPostCreate, RecruitmentCreate
from app.features.community.service import POSTS_PATH, _public_row
from app.schemas.common import ErrorCode

NOW = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)
A = CommunityActor("user-a", True)


class RacingPosts:
    """Simulates a concurrent request that committed the same claim first."""

    def __init__(self, winner: IdempotencyClaim | None = None):
        self.winner = winner
        self.private = {}
        self.public = {}

    def create(self, post, claim):
        if self.winner is not None:
            return self.winner
        self.private[post.id] = post
        self.public[post.id] = _public_row(post)
        return claim

    def get_public(self, post_id):
        return self.public.get(post_id)

    def owned_post_ids(self, author_id, post_ids):
        return {i for i in post_ids if self.private[i].author_id == author_id}


def service(repo, ids=("new-id",)):
    it = iter(ids)
    return AnonymousPostService(repo, clock=lambda: NOW, id_factory=lambda: next(it))


def payload(body="b"):
    return AnonymousPostCreate(title="제목", body=body)


def claim_for(actor_id, key, body, resource_id):
    return new_claim(
        actor_id=actor_id,
        canonical_path=POSTS_PATH,
        key=key,
        payload=payload(body).model_dump(mode="json"),
        resource_id=resource_id,
    )


def test_digest_is_order_independent_and_hex():
    assert body_digest({"a": 1, "b": "가"}) == body_digest({"b": "가", "a": 1})
    assert len(body_digest({})) == 64


def test_lost_race_with_same_body_replays_the_winner():
    repo = RacingPosts()
    original, replayed = service(repo, ids=("first",)).create(A, payload(), "k")
    assert replayed is False
    repo.winner = claim_for(A.user_id, "k", "b", original.id)
    again, replayed = service(repo, ids=("loser",)).create(A, payload(), "k")
    assert (again.id, replayed) == ("first", True)
    assert set(repo.private) == {"first"}


def test_lost_race_with_different_body_conflicts():
    repo = RacingPosts(winner=claim_for(A.user_id, "k", "other", "first"))
    with pytest.raises(ApiError) as caught:
        service(repo).create(A, payload("b"), "k")
    assert caught.value.code is ErrorCode.CONFLICT


def test_repository_returning_foreign_scope_fails_closed():
    repo = RacingPosts(winner=claim_for("user-b", "k", "b", "b-post"))
    with pytest.raises(ApiError) as caught:
        service(repo).create(A, payload(), "k")
    assert caught.value.code is ErrorCode.INTERNAL


@pytest.mark.parametrize("key", ["", " ", "x" * 129, "키"])
def test_service_rejects_invalid_key_without_writing(key):
    repo = RacingPosts()
    with pytest.raises(ApiError) as caught:
        service(repo).create(A, payload(), key)
    assert caught.value.code is ErrorCode.VALIDATION
    assert repo.private == {}


def test_unauthorized_actor_never_reaches_storage():
    class Untouchable:
        def create(self, *_):
            raise AssertionError("storage touched")

    with pytest.raises(ApiError) as caught:
        service(Untouchable()).create(CommunityActor("user-a", False), payload(), "k")
    assert caught.value.code is ErrorCode.FORBIDDEN


class Recruitments:
    def __init__(self):
        self.rows = {}

    def create(self, recruitment, claim):
        self.rows[recruitment.id] = recruitment
        return claim

    def get(self, recruitment_id):
        return self.rows.get(recruitment_id)


class Profiles:
    def display_names(self, user_ids):
        return {}


def recruitment(opportunity_id):
    return RecruitmentCreate(
        title="모집",
        body="b",
        field="개발",
        roles=["백엔드"],
        capacity=3,
        deadline_at=NOW + timedelta(days=1),
        opportunity_id=opportunity_id,
    )


def test_opportunity_link_without_provider_is_refused_before_storage():
    repo = Recruitments()
    svc = RecruitmentService(repo, Profiles(), clock=lambda: NOW, id_factory=lambda: "r1")
    with pytest.raises(ApiError) as caught:
        svc.create(A, recruitment("o1"), "k")
    assert caught.value.code is ErrorCode.VALIDATION
    assert repo.rows == {}


def test_opportunity_visibility_is_asked_for_the_current_actor():
    seen = []

    class Opportunities:
        def is_linkable(self, actor_id, opportunity_id):
            seen.append((actor_id, opportunity_id))
            return True

    repo = Recruitments()
    svc = RecruitmentService(
        repo, Profiles(), opportunities=Opportunities(), clock=lambda: NOW, id_factory=lambda: "r1"
    )
    created, _ = svc.create(A, recruitment("o1"), "k")
    assert created.opportunity_id == "o1"
    assert seen == [("user-a", "o1")]
