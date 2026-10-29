from typing import Annotated, Literal

from pydantic import Field

from app.features.public_campus.models import SourceEvidence
from app.schemas.common import ApiModel

Kind = Literal["all", "guide", "facility"]


class GuideSource(ApiModel):
    kind: Literal["official_summary"] = "official_summary"
    evidence: SourceEvidence
    snapshot_version: str


class FacilitySource(ApiModel):
    kind: Literal["unverified_facility"] = "unverified_facility"
    verification: Literal["UNKNOWN"] = "UNKNOWN"
    source_path: Literal["chatbot/data/facilities.json"] = "chatbot/data/facilities.json"
    notice: str = "기존 시설 스냅샷입니다. 공식 출처와 최신성은 검증되지 않았습니다."


class DiscoveryItem(ApiModel):
    id: str
    kind: Literal["guide", "facility"]
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(max_length=700)
    detail_path: str
    source: Annotated[GuideSource | FacilitySource, Field(discriminator="kind")]


class DiscoveryPage(ApiModel):
    query: str
    kind: Kind
    items: list[DiscoveryItem] = Field(max_length=20)
    total: int = Field(ge=0, le=200)
    counts: dict[Literal["guide", "facility"], int]
    offset: int = Field(ge=0, le=200)
    limit: int = Field(ge=1, le=20)
    complete: bool
    personal_data_access: Literal[False] = False
    generated: Literal[False] = False
    notice: str = (
        "공개 대학 안내와 시설 스냅샷만 검색합니다. "
        "개인 시간표·성적·신청·대화는 검색하지 않습니다. "
        "출처별 확인 범위가 다르며 실시간 학교 정보나 AI 생성 답변이 아닙니다."
    )
