"""공개 캠퍼스 검색만 제공하는 챗봇 통합 1단계 응답."""

from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel


class CampusSearchHit(ApiModel):
    source_id: str
    name: str
    category: str
    text: str
    building: str | None = None
    floor: str | None = None
    room: str | None = None
    hours: str | None = None
    score: float = Field(ge=0, le=1)
    matched_by: Literal["alias", "fuzzy", "keyword"]


class CampusSearchData(ApiModel):
    mode: Literal["retrieval_only"] = "retrieval_only"
    found: bool
    hits: list[CampusSearchHit]
    source: Literal["chatbot/data/facilities.json"] = "chatbot/data/facilities.json"
    verification: Literal["UNKNOWN"] = "UNKNOWN"
    source_notice: str = "기존 챗봇 시설 스냅샷이며 공식 출처와 최신성은 검증되지 않았습니다."
    generated: Literal[False] = False
    personal_data_access: Literal[False] = False
