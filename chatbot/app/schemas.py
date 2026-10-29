from typing import Literal

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


# ── 학생 개인 데이터 (data/mock/*.json, 시연용 목업) ─────────


Weekday = Literal["월", "화", "수", "목", "금", "토", "일"]
WEEKDAYS: list[str] = ["월", "화", "수", "목", "금", "토", "일"]  # datetime.weekday() 순서


class ClassSession(BaseModel):
    """강의 1회차의 요일·시간·강의실."""

    day: Weekday
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")
    building_id: str
    room: str


class Course(BaseModel):
    """개설 강의 (courses.json)."""

    course_id: str
    name: str
    credits: int
    professor: str
    sessions: list[ClassSession]


class GraduationRule(BaseModel):
    """학과별 졸업 기준 학점 (graduation.json)."""

    dept_id: str
    total: int
    by_category: dict[str, int]  # 이수 구분(전공·교양) → 최소 학점


class Student(BaseModel):
    """학생 학적·수강 정보 (students.json)."""

    student_id: str  # 학번 = 로그인 아이디
    name: str
    dept_id: str  # facilities.json의 학과 id
    grade: int
    password_hash: str  # 초기 비밀번호(주민등록번호 뒷자리)의 해시
    kakao_id: str | None = None  # 카카오 로그인 연동 시 채운다
    earned_credits: dict[str, int]  # 이수 구분 → 지금까지 취득 학점
    enrollments: list[str]  # 이번 학기 수강 course_id


class StudentData(BaseModel):
    """로드·검증이 끝난 학생 개인 데이터."""

    students: dict[str, Student]
    courses: dict[str, Course]
    rules: dict[str, GraduationRule]


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
    intent: str = "campus"  # campus | next_class | today_classes | remaining_credits
    need_login: bool = False  # 개인 질문인데 로그인하지 않았을 때 true
    latency_ms: int = 0


class LoginRequest(BaseModel):
    """/auth/login 요청. 비밀번호 초기값은 주민등록번호 뒷자리."""

    student_id: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=64)


class LoginResponse(BaseModel):
    """/auth/login 응답. 이후 요청에 `Authorization: Bearer <token>`으로 보낸다."""

    token: str
    student_id: str
    name: str
