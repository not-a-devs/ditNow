"""Fixed synthetic provenance catalog, held in process only.

This is explanation content, not a content-administration store: nothing is persisted to MariaDB,
nothing is seeded, and a restart simply rebuilds the same constants.
"""

from app.core.errors import ApiError
from app.features.data_provenance.schemas import (
    PROVENANCE_LABELS,
    ProvenanceLabel,
    ProvenanceLabelInfo,
    ProvenanceOverview,
    ProvenanceStatus,
)
from app.schemas.common import ErrorCode

CATALOG_VERSION = "data-provenance-2026-10-30-v1"

_LABELS: tuple[ProvenanceLabelInfo, ...] = (
    ProvenanceLabelInfo(
        label="DEMO",
        title="시연용 가상 데이터",
        description=(
            "시연을 위해 만든 가상의 이름·일정·기록입니다. 실제 사람이나 학적과 관계가 없습니다."
        ),
        user_guidance="실제 신청·성적·금전 처리에 사용하지 마세요.",
    ),
    ProvenanceLabelInfo(
        label="OFFICIAL_PUBLIC",
        title="공개 자료 참고 요약",
        description="누구나 볼 수 있는 공개 페이지를 참고해 이 플랫폼이 정리한 요약입니다.",
        user_guidance="최신성은 보장되지 않으므로 중요한 내용은 원문에서 다시 확인하세요.",
    ),
    ProvenanceLabelInfo(
        label="PLATFORM",
        title="플랫폼 자체 데이터",
        description="이 플랫폼 사용자가 작성했거나 플랫폼이 계산한 내용입니다.",
        user_guidance="외부 기관의 확인을 거친 내용으로 보지 마세요.",
    ),
    ProvenanceLabelInfo(
        label="UNKNOWN",
        title="출처 미확인",
        description="출처나 갱신 시점을 확인하지 못한 내용입니다.",
        user_guidance="근거가 확인되기 전까지 참고용으로만 보세요.",
    ),
)

_NOTICE = (
    "이 화면은 출처 표시의 의미를 설명할 뿐이며 "
    "출처를 등록·수정하는 관리 기능이 아닙니다. "
    "학교 통합 로그인(SSO)과 연결되어 있지 않고 "
    "어떤 금전적 효력도 없습니다."
)


def _validated(labels: tuple[ProvenanceLabelInfo, ...]) -> tuple[ProvenanceLabelInfo, ...]:
    # Fail closed: a catalog that does not describe each label exactly once is never served.
    if tuple(item.label for item in labels) != PROVENANCE_LABELS:
        raise ApiError(ErrorCode.UNAVAILABLE)
    return labels


class ProvenanceCatalog:
    def __init__(self, labels: tuple[ProvenanceLabelInfo, ...] = _LABELS) -> None:
        self._labels = labels

    def overview(self) -> ProvenanceOverview:
        labels = _validated(self._labels)
        return ProvenanceOverview(
            catalog_version=CATALOG_VERSION,
            feature_ids=["FR-ADM-004"],
            notice=_NOTICE,
            status=ProvenanceStatus(),
            labels=[item.model_copy() for item in labels],
        )

    def label(self, label: ProvenanceLabel) -> ProvenanceLabelInfo:
        for item in _validated(self._labels):
            if item.label == label:
                return item.model_copy()
        raise ApiError(ErrorCode.NOT_FOUND)


def fixed_catalog() -> ProvenanceCatalog:
    return ProvenanceCatalog()
