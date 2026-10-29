"""Deterministic FR-OPP-002 matching and the rule-based FR-AI-002/003 subset.

No model call, vendor or learned ranking: fixed rules over the approved API-OPP projection,
the verified actor's current memberships and interests sent with the request (not stored).
Matching narrows display only. It never decides eligibility; the original notice does.
"""

import hashlib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID

from pydantic import ValidationError

from app.core.errors import ApiError
from app.features.campus.domain import MAX_GRADE, MIN_GRADE
from app.features.community.domain import Recruitment, RecruitmentStatus, effective_status
from app.features.opportunities.repository import (
    OpportunityCatalog,
    OpportunityQuery,
    OpportunityRecord,
)
from app.features.opportunities.schemas import (
    OpportunityKind,
    PublicationStatus,
    SourceKind,
    SubmissionMode,
)
from app.features.opportunities.service import MAX_LIMIT, matches, safe_url, to_detail, to_summary
from app.features.opportunity_matching.models import (
    Caution,
    CautionCode,
    ContextBasis,
    Freshness,
    MatchItem,
    MatchPage,
    MatchReason,
    MatchSummary,
    MembershipData,
    OpportunityBrief,
    ProcedureStep,
    ReasonCode,
    RecruitmentRef,
    RecruitmentRefs,
    StepCode,
    Window,
)
from app.features.opportunity_matching.ports import (
    AcademicContext,
    AcademicContextReader,
    AcademicMembership,
    RecruitmentReferenceReader,
)
from app.schemas.common import ErrorCode

# Design defaults for the demo, not approved school policy values.
MAX_CANDIDATES = 200
CATALOG_PAGE_SIZE = MAX_LIMIT
MAX_CATALOG_PAGES = MAX_CANDIDATES // CATALOG_PAGE_SIZE + 1
MAX_PAGE_LIMIT = 20
MAX_INTERESTS = 5
MAX_KEYWORD_LENGTH = 20
MAX_RECRUITMENT_REFS = 3
MAX_PROCEDURE_FILES = 10
STALE_AFTER = timedelta(days=30)
DEADLINE_SOON = timedelta(days=7)
# Only the first two matched keywords add score so long keyword lists cannot dominate.
MAX_SCORED_KEYWORDS = 2

SCORES: dict[ReasonCode, int] = {
    ReasonCode.GRADE_MATCH: 30,
    ReasonCode.DEPARTMENT_MATCH: 20,
    ReasonCode.KIND_INTEREST: 15,
    ReasonCode.SCHOOL_WIDE: 10,
    ReasonCode.KEYWORD_INTEREST: 10,
    ReasonCode.DEADLINE_SOON: 5,
}

_CODE = re.compile(r"^[A-Za-z0-9_-]{1,20}$")
_CURSOR = re.compile(r"^(?P<offset>[0-9]{1,4})\.(?P<digest>[0-9a-f]{16})$")


@dataclass(frozen=True)
class Interests:
    kinds: tuple[OpportunityKind, ...] = ()
    keywords: tuple[str, ...] = ()


def normalize_interests(kinds: Sequence[OpportunityKind], keywords: Sequence[str]) -> Interests:
    """Validate caller interests. They are request input only and are never persisted."""
    if len(kinds) > MAX_INTERESTS or len(keywords) > MAX_INTERESTS:
        raise ApiError(ErrorCode.VALIDATION)
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in keywords:
        word = raw.strip()
        if not 1 <= len(word) <= MAX_KEYWORD_LENGTH or not word.isprintable():
            raise ApiError(ErrorCode.VALIDATION)
        if word.casefold() not in seen:
            seen.add(word.casefold())
            cleaned.append(word)
    return Interests(kinds=tuple(dict.fromkeys(kinds)), keywords=tuple(cleaned))


def _aware(value: datetime | None) -> bool:
    return value is None or (value.tzinfo is not None and value.utcoffset() is not None)


def is_well_formed(record: OpportunityRecord, now: datetime) -> bool:
    """Rows that cannot be judged safely are omitted instead of guessed."""
    if not (record.title.strip() and record.organization.strip()):
        return False
    stamps = (record.apply_starts_at, record.deadline_at, record.checked_at)
    if not all(_aware(stamp) for stamp in stamps):
        return False
    if (
        record.apply_starts_at
        and record.deadline_at
        and record.apply_starts_at > record.deadline_at
    ):
        return False
    if record.checked_at is not None and record.checked_at > now:
        return False
    scope = record.target_scope
    if scope.level == "school":
        return not scope.department_codes and not scope.academic_years
    if scope.level == "department":
        return bool(scope.department_codes) and not scope.academic_years
    if scope.level == "grade":
        return bool(scope.academic_years) and all(
            MIN_GRADE <= year <= MAX_GRADE for year in scope.academic_years
        )
    return False


def window_of(record: OpportunityRecord, now: datetime) -> Window:
    if record.deadline_at is not None and record.deadline_at <= now:
        return Window.CLOSED
    if record.apply_starts_at is not None and record.apply_starts_at > now:
        return Window.UPCOMING
    return Window.NO_DEADLINE if record.deadline_at is None else Window.OPEN


def freshness_of(record: OpportunityRecord, now: datetime) -> Freshness:
    if record.checked_at is None:
        return Freshness.UNVERIFIED
    return Freshness.STALE if now - record.checked_at > STALE_AFTER else Freshness.CURRENT


def scope_reasons(
    record: OpportunityRecord, memberships: Sequence[AcademicMembership]
) -> list[MatchReason] | None:
    """Target-scope reasons, or None when no current membership falls inside the scope."""
    scope = record.target_scope
    if scope.level == "school":
        return [MatchReason(code=ReasonCode.SCHOOL_WIDE, source_field="target_scope.level")]
    codes = set(scope.department_codes)
    if scope.level == "department":
        hits = sorted(codes & {m.department_code for m in memberships})
        if not hits:
            return None
        return [
            MatchReason(
                code=ReasonCode.DEPARTMENT_MATCH,
                source_field="target_scope.department_codes",
                value=hits[0],
            )
        ]
    # grade: year must match within the same membership; an empty code list means any department.
    for m in memberships:
        if m.grade in scope.academic_years and (not codes or m.department_code in codes):
            reasons = []
            if codes:
                reasons.append(
                    MatchReason(
                        code=ReasonCode.DEPARTMENT_MATCH,
                        source_field="target_scope.department_codes",
                        value=m.department_code,
                    )
                )
            reasons.append(
                MatchReason(
                    code=ReasonCode.GRADE_MATCH,
                    source_field="target_scope.academic_years",
                    value=str(m.grade),
                )
            )
            return reasons
    return None


def interest_reasons(record: OpportunityRecord, interests: Interests) -> list[MatchReason]:
    reasons: list[MatchReason] = []
    if record.kind in interests.kinds:
        reasons.append(
            MatchReason(code=ReasonCode.KIND_INTEREST, source_field="kind", value=record.kind.value)
        )
    fields = (
        ("title", record.title),
        ("organization", record.organization),
        ("eligibility", record.eligibility),
    )
    for word in interests.keywords:
        needle = word.casefold()
        for name, text in fields:
            if needle in text.casefold():
                reasons.append(
                    MatchReason(code=ReasonCode.KEYWORD_INTEREST, source_field=name, value=word)
                )
                break
    return reasons


def score_of(reasons: Sequence[MatchReason]) -> int:
    keyword_hits = 0
    total = 0
    for reason in reasons:
        if reason.code is ReasonCode.KEYWORD_INTEREST:
            keyword_hits += 1
            if keyword_hits > MAX_SCORED_KEYWORDS:
                continue
        total += SCORES[reason.code]
    return total


def procedure_of(record: OpportunityRecord) -> list[ProcedureStep]:
    """Fixed template per submission mode; every step points at the original field it uses."""
    steps: list[ProcedureStep] = []

    def add(code: StepCode, available: bool, field: str, value=None, url=None) -> None:
        steps.append(
            ProcedureStep(
                order=len(steps) + 1,
                code=code,
                available=available,
                evidence_field=field,
                evidence_value=value,
                evidence_url=url,
            )
        )

    original = safe_url(record.original_url)
    source = safe_url(record.source_url)
    add(
        StepCode.CHECK_ORIGINAL,
        (original or source) is not None,
        "source_url" if original is None and source else "original_url",
        url=original or source,
    )
    mode = record.submission_mode
    if mode is SubmissionMode.EXTERNAL_DOCUMENT_SUBMISSION:
        files = record.files[:MAX_PROCEDURE_FILES]
        if not files:
            add(StepCode.DOWNLOAD_FORM, False, "files")
        for item in files:
            url = safe_url(item.original_url)
            add(StepCode.DOWNLOAD_FORM, url is not None, "files", item.filename, url)
        add(
            StepCode.SUBMIT_TO_DESTINATION,
            bool(record.destination),
            "destination",
            record.destination or None,
        )
    elif mode is SubmissionMode.EXTERNAL_LINK:
        add(StepCode.APPLY_VIA_LINK, original is not None, "original_url", url=original)
    if mode is not SubmissionMode.INFO_ONLY:
        add(StepCode.SELF_RECORD, True, "submission_mode", mode.value)
    return steps


def cautions_of(
    record: OpportunityRecord,
    needs_verification: bool,
    window: Window,
    freshness: Freshness,
    in_scope: bool,
) -> list[Caution]:
    codes = [CautionCode.NOT_ELIGIBILITY_DECISION]
    if record.submission_mode is SubmissionMode.INFO_ONLY:
        codes.append(CautionCode.NO_APPLICATION_PROCEDURE)
    else:
        codes.append(CautionCode.EXTERNAL_SUBMISSION)
    if record.source_kind is SourceKind.DEMO:
        codes.append(CautionCode.DEMO_SOURCE)
    if needs_verification:
        codes.append(CautionCode.NEEDS_VERIFICATION)
    if freshness is Freshness.STALE:
        codes.append(CautionCode.STALE_SOURCE)
    elif freshness is Freshness.UNVERIFIED:
        codes.append(CautionCode.UNVERIFIED_SOURCE)
    if window is Window.CLOSED:
        codes.append(CautionCode.DEADLINE_PASSED)
    elif window is Window.UPCOMING:
        codes.append(CautionCode.NOT_YET_OPEN)
    if not in_scope:
        codes.append(CautionCode.OUT_OF_SCOPE)
    return [Caution(code=code) for code in codes]


def _clean_memberships(context: AcademicContext) -> tuple[AcademicMembership, ...]:
    valid = {
        m
        for m in context.memberships
        if _CODE.fullmatch(m.department_code)
        and (m.grade is None or MIN_GRADE <= m.grade <= MAX_GRADE)
    }
    return tuple(sorted(valid, key=lambda m: (m.department_code, m.grade or 0)))


@dataclass(frozen=True)
class _Ranked:
    record: OpportunityRecord
    item: MatchItem


def _sort_key(entry: _Ranked) -> tuple:
    deadline = entry.record.deadline_at
    return (
        -entry.item.score,
        deadline is None,
        deadline.timestamp() if deadline else 0.0,
        str(entry.record.id),
    )


class MatchingService:
    def __init__(
        self,
        catalog: OpportunityCatalog,
        contexts: AcademicContextReader,
        recruitments: RecruitmentReferenceReader | None,
        *,
        clock: Callable[[], datetime],
    ):
        self._catalog = catalog
        self._contexts = contexts
        self._recruitments = recruitments
        self._now = clock()

    # ---- actor context ----

    def _context(self, user_id: UUID) -> tuple[AcademicMembership, ...]:
        context = self._contexts.current(user_id)
        # Never evaluate with a context that belongs to anyone but the verified principal.
        if context is None or context.user_id != user_id:
            raise ApiError(ErrorCode.FORBIDDEN)
        return _clean_memberships(context)

    @staticmethod
    def _basis(memberships, interests: Interests) -> ContextBasis:
        return ContextBasis(
            memberships=[
                MembershipData(department_code=m.department_code, grade=m.grade)
                for m in memberships
            ],
            interest_kinds=list(interests.kinds),
            interest_keywords=list(interests.keywords),
        )

    # ---- candidate scan ----

    def _scan(self, query: OpportunityQuery) -> tuple[list[OpportunityRecord], int, bool]:
        """Read at most MAX_CANDIDATES rows from the catalog; report whether the scan finished."""
        rows: list[OpportunityRecord] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        for _ in range(MAX_CATALOG_PAGES):
            page = self._catalog.list_public(replace(query, cursor=cursor), self._now)
            items = list(page.items)
            for record in items[:CATALOG_PAGE_SIZE]:
                if len(rows) >= MAX_CANDIDATES:
                    return rows, len(rows), False
                rows.append(record)
            # An adapter that ignores the page size cannot prove the scan was complete.
            if len(items) > CATALOG_PAGE_SIZE:
                return rows, len(rows), False
            if page.next_cursor is None:
                return rows, len(rows), True
            if page.next_cursor in seen_cursors or len(rows) >= MAX_CANDIDATES:
                return rows, len(rows), False
            seen_cursors.add(page.next_cursor)
            cursor = page.next_cursor
        return rows, len(rows), False

    def _evaluate(
        self,
        record: OpportunityRecord,
        memberships: Sequence[AcademicMembership],
        interests: Interests,
    ) -> MatchItem | None:
        """Matched item, or None when out of scope. Raises ValueError for malformed rows."""
        if not is_well_formed(record, self._now):
            raise ValueError("malformed")
        scope = scope_reasons(record, memberships)
        if scope is None:
            return None
        window = window_of(record, self._now)
        reasons = scope + interest_reasons(record, interests)
        if (
            window is Window.OPEN
            and record.deadline_at is not None
            and record.deadline_at - self._now <= DEADLINE_SOON
        ):
            reasons.append(MatchReason(code=ReasonCode.DEADLINE_SOON, source_field="deadline_at"))
        return MatchItem(
            opportunity=to_summary(record, self._now),
            score=score_of(reasons),
            reasons=reasons,
            window=window,
            freshness=freshness_of(record, self._now),
            checked_at=record.checked_at,
            source_url=safe_url(record.original_url) or safe_url(record.source_url),
            recruitment=RecruitmentRefs(status="NOT_CONNECTED"),
        )

    # ---- FR-OPP-002 / FR-AI-003 list ----

    def list_matches(
        self,
        user_id: UUID,
        interests: Interests,
        *,
        kind: OpportunityKind | None,
        include_closed: bool,
        limit: int,
        cursor: str | None,
    ) -> MatchPage:
        if not 1 <= limit <= MAX_PAGE_LIMIT:
            raise ApiError(ErrorCode.VALIDATION)
        memberships = self._context(user_id)
        query = OpportunityQuery(kind=kind, open_only=not include_closed, limit=CATALOG_PAGE_SIZE)
        rows, scanned, complete = self._scan(query)

        ranked: list[_Ranked] = []
        seen: set[UUID] = set()
        omitted = 0
        for record in rows:
            try:
                if record.id in seen:
                    omitted += 1
                    continue
                seen.add(record.id)
                # Defense in depth: drop anything the adapter returned that is not public.
                if not matches(record, query, self._now):
                    continue
                item = self._evaluate(record, memberships, interests)
            except (ValueError, TypeError, AttributeError, ValidationError):
                omitted += 1
                continue
            if item is not None:
                ranked.append(_Ranked(record, item))
        ranked.sort(key=_sort_key)

        digest = self._digest(ranked, kind, include_closed, interests)
        offset = self._offset(cursor, digest, len(ranked))
        window = ranked[offset : offset + limit]
        end = offset + len(window)
        items = self._attach_recruitment([entry.item for entry in window], interests)
        return MatchPage(
            items=items,
            next_cursor=f"{end}.{digest}" if end < len(ranked) else None,
            candidate_cap=MAX_CANDIDATES,
            candidates_scanned=scanned,
            complete=complete,
            omitted_count=omitted,
            context=self._basis(memberships, interests),
            evaluated_at=self._now,
        )

    @staticmethod
    def _digest(ranked, kind, include_closed, interests: Interests) -> str:
        parts = [f"{kind or ''}|{include_closed}|{','.join(interests.kinds)}"]
        parts.append("\x1f".join(word.casefold() for word in interests.keywords))
        parts.extend(f"{entry.record.id}:{entry.item.score}" for entry in ranked)
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]

    @staticmethod
    def _offset(cursor: str | None, digest: str, total: int) -> int:
        if cursor is None:
            return 0
        match = _CURSOR.fullmatch(cursor)
        if match is None:
            raise ApiError(ErrorCode.VALIDATION)
        # The ranking or the request changed since the cursor was issued: restart, don't skip.
        if match["digest"] != digest:
            raise ApiError(ErrorCode.CONFLICT)
        offset = int(match["offset"])
        if not 0 < offset < total:
            raise ApiError(ErrorCode.VALIDATION)
        return offset

    # ---- recruitment reference seam (FR-OPP-005 link, FR-AI-003 relevance) ----

    def _recruitment_refs(
        self, opportunity_ids: Sequence[UUID], interests: Interests
    ) -> dict[UUID, RecruitmentRefs]:
        if self._recruitments is None:
            return {oid: RecruitmentRefs(status="NOT_CONNECTED") for oid in opportunity_ids}
        try:
            rows = list(self._recruitments.linked_recruitments(list(opportunity_ids), self._now))
        except Exception:
            # Auxiliary data: the match list stays usable; no adapter detail is exposed.
            return {oid: RecruitmentRefs(status="UNAVAILABLE") for oid in opportunity_ids}
        by_key = {str(oid): oid for oid in opportunity_ids}
        grouped: dict[UUID, list[RecruitmentRef]] = {oid: [] for oid in opportunity_ids}
        seen: set[str] = set()
        for row in rows:
            ref = self._project_recruitment(row, by_key, interests)
            if ref is not None and ref[1].id not in seen:
                seen.add(ref[1].id)
                grouped[ref[0]].append(ref[1])
        result = {}
        for oid, refs in grouped.items():
            refs.sort(key=lambda r: (r.deadline_at, r.id))
            result[oid] = RecruitmentRefs(
                status="AVAILABLE", open_count=len(refs), items=refs[:MAX_RECRUITMENT_REFS]
            )
        return result

    def _project_recruitment(
        self, row: Recruitment, by_key: dict[str, UUID], interests: Interests
    ) -> tuple[UUID, RecruitmentRef] | None:
        try:
            oid = by_key.get((row.opportunity_id or "").lower())
            if oid is None or not _aware(row.deadline_at):
                return None
            if effective_status(row, self._now) is not RecruitmentStatus.OPEN:
                return None
            haystack = "\n".join((row.title, row.field, *row.roles)).casefold()
            return oid, RecruitmentRef(
                id=row.id,
                title=row.title,
                field=row.field,
                roles=list(row.roles),
                deadline_at=row.deadline_at,
                matched_keywords=[w for w in interests.keywords if w.casefold() in haystack],
            )
        except (ValueError, TypeError, AttributeError, ValidationError):
            return None

    def _attach_recruitment(self, items: list[MatchItem], interests: Interests) -> list[MatchItem]:
        if not items:
            return items
        refs = self._recruitment_refs([item.opportunity.id for item in items], interests)
        return [
            item.model_copy(update={"recruitment": refs[item.opportunity.id]}) for item in items
        ]

    # ---- FR-AI-002 structured brief ----

    def brief(self, user_id: UUID, opportunity_id: UUID, interests: Interests) -> OpportunityBrief:
        memberships = self._context(user_id)
        record = self._catalog.get(opportunity_id)
        if record is None or record.status is not PublicationStatus.PUBLISHED:
            raise ApiError(ErrorCode.NOT_FOUND)
        try:
            if record.id != opportunity_id or not is_well_formed(record, self._now):
                raise ValueError("malformed")
            detail = to_detail(record, self._now)
            scope = scope_reasons(record, memberships)
            window = window_of(record, self._now)
            freshness = freshness_of(record, self._now)
            procedure = procedure_of(record)
        except (ValueError, TypeError, AttributeError, ValidationError):
            # Same response as a missing row: nothing about the malformed record leaks.
            raise ApiError(ErrorCode.NOT_FOUND) from None
        reasons = (scope or []) + interest_reasons(record, interests)
        refs = self._recruitment_refs([record.id], interests)[record.id]
        return OpportunityBrief(
            opportunity=detail,
            match=MatchSummary(
                in_scope=scope is not None, score=score_of(reasons), reasons=reasons
            ),
            window=window,
            freshness=freshness,
            procedure=procedure,
            cautions=cautions_of(
                record, detail.needs_verification, window, freshness, scope is not None
            ),
            recruitment=refs,
            context=self._basis(memberships, interests),
            evaluated_at=self._now,
        )
