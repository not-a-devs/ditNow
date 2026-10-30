"""Bounded in-memory demo ledger, deliberately unrelated to MariaDB and official records."""

import re
from dataclasses import dataclass
from threading import RLock
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.features.demo_services.models import (
    AdvanceInput,
    CreateInput,
    DeletedDemo,
    DemoActor,
    DemoItem,
    DemoKind,
    DemoPage,
    DemoScenario,
    DemoStatus,
)
from app.schemas.common import ErrorCode, utc_now

# Technical memory bounds, not university quotas. Tombstones/claims are never evicted into replay.
MAX_OWNER_RECORDS = 20
MAX_RECORDS = 200
MAX_CLAIMS = 1000
KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,100}\Z")

TITLES = {
    DemoKind.ADMISSION_RESULT: "가상 입학 결과 확인",
    DemoKind.ADMISSION_WITHDRAWAL: "가상 등록포기·환불 상태",
    DemoKind.CERTIFICATE: "시연용 증명서",
    DemoKind.TUITION: "가상 등록금 납부 확인",
    DemoKind.PROTECTED_COUNSEL: "가상 보호상담 절차",
}
STATUS_LABELS = {
    DemoStatus.REQUESTED: "가상 신청 생성",
    DemoStatus.IN_PROGRESS: "가상 처리 단계",
    DemoStatus.COMPLETED: "가상 시연 완료",
}
OUTCOMES = {
    DemoKind.ADMISSION_RESULT: "가상 결과 화면 예시입니다. 실제 합격·입학 자격이 아닙니다.",
    DemoKind.ADMISSION_WITHDRAWAL: (
        "가상 포기·환불 상태 예시입니다. 등록 취소나 금융 거래는 없습니다."
    ),
    DemoKind.CERTIFICATE: "시연용 문구만 표시합니다. 학교 발급·직인·진본 검증은 없습니다.",
    DemoKind.TUITION: "가상 납부 확인 예시입니다. 금액·계좌 입력이나 실제 결제는 없습니다.",
    DemoKind.PROTECTED_COUNSEL: (
        "고정 선택형 가상 상담 절차가 끝났습니다. 실제 고충 접수는 없습니다."
    ),
}
DEMO_DOCUMENT = (
    "시연용 증명서 — 가상 학생의 화면 시연 문서입니다. "
    "학교 공식 발급물이 아니며 직인·서명·공식 효력이 없습니다."
)


@dataclass(frozen=True, slots=True)
class _Record:
    owner: UUID
    item: DemoItem
    deleted_at_revision: int | None = None


class DemoServices:
    """One app-owned instance. RLock covers ownership, CAS, claims and writes together.

    No globals, auto-provisioning, network, logging or persistent database. Restart clears all
    records; multiple workers have separate ledgers. Shared production persistence is NOT_RUN.
    """

    def __init__(self) -> None:
        self._records: dict[UUID, _Record] = {}
        self._claims: dict[tuple[UUID, str, str], tuple[tuple, DemoItem]] = {}
        self._lock = RLock()

    @staticmethod
    def _actor(actor: DemoActor) -> UUID:
        if not isinstance(actor, DemoActor) or not isinstance(actor.user_id, UUID):
            raise ApiError(ErrorCode.UNAVAILABLE)
        return actor.user_id

    def _owned(self, owner: UUID, identifier: UUID) -> _Record:
        row = self._records.get(identifier)
        if row is None or row.owner != owner:
            raise ApiError(ErrorCode.NOT_FOUND)
        return row

    def _claim(self, owner: UUID, operation: str, key: str, payload: tuple) -> DemoItem | None:
        if not isinstance(key, str) or not KEY_PATTERN.fullmatch(key):
            raise ApiError(ErrorCode.VALIDATION)
        prior = self._claims.get((owner, operation, key))
        if prior is not None:
            fingerprint, item = prior
            if (
                fingerprint != payload
                or self._owned(owner, item.id).deleted_at_revision is not None
            ):
                raise ApiError(ErrorCode.CONFLICT)
            return item
        if len(self._claims) >= MAX_CLAIMS:
            raise ApiError(ErrorCode.RATE_LIMITED)
        return None

    def list(self, actor: DemoActor) -> DemoPage:
        owner = self._actor(actor)
        with self._lock:
            return DemoPage(
                items=[
                    row.item
                    for row in reversed(tuple(self._records.values()))
                    if row.owner == owner and row.deleted_at_revision is None
                ]
            )

    def create(self, actor: DemoActor, body: CreateInput, key: str) -> DemoItem:
        owner = self._actor(actor)
        payload = (body.kind, body.scenario, body.consent)
        with self._lock:
            if prior := self._claim(owner, "create", key, payload):
                return prior
            if (
                len(self._records) >= MAX_RECORDS
                or sum(row.owner == owner for row in self._records.values()) >= MAX_OWNER_RECORDS
            ):
                raise ApiError(ErrorCode.RATE_LIMITED)
            now = utc_now()
            item = DemoItem(
                id=uuid4(),
                kind=body.kind,
                scenario=body.scenario,
                status=DemoStatus.REQUESTED,
                status_label=STATUS_LABELS[DemoStatus.REQUESTED],
                title=TITLES[body.kind],
                revision=1,
                created_at=now,
                updated_at=now,
            )
            self._records[item.id] = _Record(owner, item)
            self._claims[(owner, "create", key)] = (payload, item)
            return item

    def advance(self, actor: DemoActor, identifier: UUID, body: AdvanceInput, key: str) -> DemoItem:
        owner = self._actor(actor)
        with self._lock:
            row = self._owned(owner, identifier)
            if row.deleted_at_revision is not None:
                raise ApiError(ErrorCode.NOT_FOUND)
            operation = f"advance:{identifier}"
            if prior := self._claim(owner, operation, key, (body.revision,)):
                return prior
            if row.item.revision != body.revision or row.item.status is DemoStatus.COMPLETED:
                raise ApiError(ErrorCode.CONFLICT)
            status = (
                DemoStatus.IN_PROGRESS
                if row.item.status is DemoStatus.REQUESTED
                else DemoStatus.COMPLETED
            )
            outcome = None
            if status is DemoStatus.COMPLETED:
                scenario_label = (
                    "기본 가상 예시"
                    if row.item.scenario is DemoScenario.STANDARD
                    else "추가 검토 가상 예시"
                )
                outcome = f"{scenario_label}: {OUTCOMES[row.item.kind]}"
            item = row.item.model_copy(
                update={
                    "status": status,
                    "status_label": STATUS_LABELS[status],
                    "revision": row.item.revision + 1,
                    "updated_at": utc_now(),
                    "outcome_text": outcome,
                    "document_text": DEMO_DOCUMENT
                    if status is DemoStatus.COMPLETED and row.item.kind is DemoKind.CERTIFICATE
                    else None,
                }
            )
            self._records[identifier] = _Record(owner, item)
            self._claims[(owner, operation, key)] = ((body.revision,), item)
            return item

    def delete(self, actor: DemoActor, identifier: UUID, revision: int) -> DeletedDemo:
        owner = self._actor(actor)
        if type(revision) is not int or not 1 <= revision <= 2_147_483_647:
            raise ApiError(ErrorCode.VALIDATION)
        with self._lock:
            row = self._owned(owner, identifier)
            if row.deleted_at_revision is not None:
                if row.deleted_at_revision != revision:
                    raise ApiError(ErrorCode.CONFLICT)
                return DeletedDemo(id=identifier)
            if row.item.revision != revision:
                raise ApiError(ErrorCode.CONFLICT)
            self._records[identifier] = _Record(owner, row.item, revision)
            return DeletedDemo(id=identifier)
