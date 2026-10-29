from pydantic import BaseModel, Field

# ── 데이터 모델 (data/*.json) ──────────────────────────────


class Building(BaseModel):
    """건물 위치 정보 (buildings.json)."""

    building_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    address: str | None = None
    lat: float | None = None
    lng: float | None = None


class Facility(BaseModel):
    """검색 대상 문서: 건물·학과사무실·행정부서·편의시설·식당 (facilities.json)."""

    id: str
    category: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    building: str | None = None
    building_id: str | None = None
    floor: str | None = None
    room: str | None = None
    phone: str | None = None
    hours: str | None = None
    note: str | None = None
    text: str

    def to_search_text(self) -> str:
        """키워드 검색에 사용할 텍스트를 만든다."""
        parts = [self.name, *self.aliases, self.category, self.building, self.text, self.note]
        return " ".join(p for p in parts if p)

    def to_context(self) -> str:
        """LLM에 넘길 사람이 읽기 좋은 짧은 텍스트를 만든다."""
        head = f"[{self.id}] {self.name} ({self.category})"
        if self.aliases:
            head += f" (별칭: {', '.join(self.aliases)})"
        lines = [head, f"- 설명: {self.text}"]
        place = " ".join(p for p in [self.building, self.floor, self.room] if p)
        if place:
            lines.append(f"- 위치: {place}")
        if self.hours:
            lines.append(f"- 운영: {self.hours}")
        if self.phone:
            lines.append(f"- 전화: {self.phone}")
        if self.note:
            lines.append(f"- 참고: {self.note}")
        return "\n".join(lines)


class CampusData(BaseModel):
    """로드·검증이 끝난 전체 데이터."""

    facilities: dict[str, Facility]
    buildings: dict[str, Building]


# ── API 모델 ──────────────────────────────────────────────


class UserLocation(BaseModel):
    """사용자 현재 위치 (이후 길찾기용, 로그에 남기지 않음)."""

    lat: float
    lng: float


class AskRequest(BaseModel):
    """/ask 요청."""

    question: str = Field(min_length=1, max_length=200)
    user_location: UserLocation | None = None


class LocationOut(BaseModel):
    """지도에 표시할 근거 시설의 좌표."""

    id: str
    name: str
    building: str
    lat: float
    lng: float


class AskResponse(BaseModel):
    """/ask 응답."""

    answer: str
    sources: list[str] = Field(default_factory=list)
    locations: list[LocationOut] = Field(default_factory=list)
    found: bool
    latency_ms: int = 0
