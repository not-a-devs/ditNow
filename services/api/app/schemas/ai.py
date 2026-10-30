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


class AskTurn(ApiModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1000)


class AskUserLocation(ApiModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class AskInput(ApiModel):
    question: str = Field(min_length=1, max_length=200)
    history: list[AskTurn] = Field(default_factory=list, max_length=6)
    # 도보 예상 시간 계산에만 쓴다. 저장·로그·LLM 전송하지 않는다
    user_location: AskUserLocation | None = None


class AskLocation(ApiModel):
    id: str
    name: str
    building: str
    lat: float
    lng: float
    distance_m: int | None = None
    walk_minutes: int | None = None


class AskData(ApiModel):
    answer: str
    sources: list[str]
    locations: list[AskLocation]
    found: bool
    intent: str
    need_login: bool
    classified_by: Literal["keyword", "llm"]
    rewritten_question: str | None = None
    generated: Literal[True] = True
    personal_data_access: bool
    record_source: Literal["DEMO"] = "DEMO"
