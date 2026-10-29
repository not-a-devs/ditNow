"""로그인한 학생의 개인 질문 처리기.

숫자·시간 계산은 여기서 코드로 끝내고, LLM에는 확정된 사실만 <context>로 넘긴다.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.retriever.keyword import normalize, tokenize
from app.schemas import (
    WEEKDAYS,
    CampusData,
    ClassSession,
    Course,
    LocationOut,
    Student,
    StudentData,
)

KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없어 고정 오프셋으로 충분하다

Result = tuple[list[str], list[LocationOut]]  # (<context> 블록들, 지도 좌표 후보)


@dataclass(frozen=True)
class PersonalQuery:
    """처리기에 넘기는 질문과 조건값."""

    question: str
    now: datetime
    day: str | None = None  # intents.extract_day 값: "월"~"일" | "오늘" | "내일" | "모레" | "week"


Handler = Callable[[Student, StudentData, CampusData, PersonalQuery], Result]
_RELATIVE_DAYS = {"오늘": 0, "내일": 1, "모레": 2}


def _courses(student: Student, sd: StudentData) -> list[Course]:
    """이번 학기 수강 과목."""
    return [sd.courses[i] for i in student.enrollments]


def match_courses(question: str, courses: list[Course]) -> list[Course]:
    """질문에 이름이 나온 과목. '자료구조 강의실'·'진로 수업'처럼 과목명 일부만 써도 찾는다."""
    compact = normalize(question).replace(" ", "")
    words = [w for w in tokenize(question) if len(w) >= 2]
    out = []
    for c in courses:
        name = normalize(c.name).replace(" ", "")
        if name in compact or any(w in name for w in words):
            out.append(c)
    return out


def _classes(courses: list[Course]) -> list[tuple[Course, ClassSession]]:
    """과목들의 모든 강의 회차."""
    return [(c, s) for c in courses for s in c.sessions]


def _days(q: PersonalQuery) -> list[str] | None:
    """요일 조건을 실제 요일 목록으로 바꾼다. 조건이 없으면 None."""
    if q.day is None:
        return None
    if q.day == "week":
        return WEEKDAYS
    if q.day in _RELATIVE_DAYS:
        return [WEEKDAYS[(q.now.weekday() + _RELATIVE_DAYS[q.day]) % 7]]
    return [q.day]


def _describe(course: Course, s: ClassSession, campus: CampusData, label: str) -> str:
    """강의 회차를 컨텍스트 블록으로 만든다."""
    building = campus.buildings[s.building_id].name
    return (
        f"[{course.course_id}] {label}: {course.name} "
        f"(담당 {course.professor}, {course.credits}학점)\n"
        f"- 시간: {s.day}요일 {s.start}~{s.end}\n"
        f"- 강의실: {building} {s.room}"
    )


def _location(course: Course, s: ClassSession, campus: CampusData) -> list[LocationOut]:
    """강의실 건물에 좌표가 있으면 지도 표시용으로 돌려준다."""
    b = campus.buildings[s.building_id]
    if b.lat is None or b.lng is None:
        return []
    return [
        LocationOut(id=course.course_id, name=course.name, building=b.name, lat=b.lat, lng=b.lng)
    ]


def next_class(student: Student, sd: StudentData, campus: CampusData, q: PersonalQuery) -> Result:
    """지금 이후 가장 먼저 시작하는 수업 (일주일 뒤 같은 요일까지). 과목을 말하면 그 과목만."""
    courses = _courses(student, sd)
    classes = _classes(match_courses(q.question, courses) or courses)
    now = q.now
    hhmm = now.strftime("%H:%M")
    for offset in range(8):
        day_index = now.weekday() + offset
        day = WEEKDAYS[day_index % 7]
        todays = sorted((cs for cs in classes if cs[1].day == day), key=lambda cs: cs[1].start)
        for course, s in todays:
            if offset == 0 and s.start <= hhmm:
                continue
            if offset <= 1:
                when = ["오늘", "내일"][offset]
            else:
                when = f"{'다음 주 ' if day_index >= 7 else ''}{day}요일"
            label = f"다음 수업({when}, 현재 {WEEKDAYS[now.weekday()]}요일 {hhmm} 기준)"
            return [_describe(course, s, campus, label)], _location(course, s, campus)
    return [f"[my_timetable] {student.name} 학생은 이번 학기 예정된 수업이 없습니다."], []


def day_classes(student: Student, sd: StudentData, campus: CampusData, q: PersonalQuery) -> Result:
    """특정 날(기본 오늘)의 수업. 과목만 말하면('자료구조 무슨 요일') 그 과목의 일주일 전체."""
    courses = _courses(student, sd)
    named = match_courses(q.question, courses)
    days = _days(q) or (WEEKDAYS if named else [WEEKDAYS[q.now.weekday()]])
    today = WEEKDAYS[q.now.weekday()]
    if days == WEEKDAYS:
        label = "이번 주"
    elif q.day in _RELATIVE_DAYS or days == [today]:
        label = f"{q.day if q.day in _RELATIVE_DAYS else '오늘'}({days[0]}요일)"
    else:
        label = f"{days[0]}요일"
    picked = sorted(
        (cs for cs in _classes(named or courses) if cs[1].day in days),
        key=lambda cs: (WEEKDAYS.index(cs[1].day), cs[1].start),
    )
    if not picked:
        return [f"[my_timetable] {label} {student.name} 학생의 수업이 없습니다."], []
    blocks = [_describe(c, s, campus, f"{label} 수업") for c, s in picked]
    return blocks, [loc for c, s in picked for loc in _location(c, s, campus)]


def remaining_credits(
    student: Student, sd: StudentData, campus: CampusData, q: PersonalQuery
) -> Result:
    """졸업 기준 대비 남은 학점을 계산한다."""
    rule = sd.rules[student.dept_id]
    earned_total = sum(student.earned_credits.values())
    lines = [
        f"[my_credits] {student.name} 학생 ({campus.facilities[student.dept_id].name} "
        f"{student.grade}학년) 졸업 학점 현황",
        f"- 졸업 기준: 총 {rule.total}학점 "
        f"({', '.join(f'{k} {v}학점 이상' for k, v in rule.by_category.items())})",
        f"- 지금까지 취득: 총 {earned_total}학점 "
        f"({', '.join(f'{k} {v}학점' for k, v in student.earned_credits.items())})",
        f"- 남은 학점: 총 {max(0, rule.total - earned_total)}학점",
    ]
    for category, need in rule.by_category.items():
        left = max(0, need - student.earned_credits.get(category, 0))
        lines.append(f"- 남은 {category}: {left}학점" + (" (충족)" if left == 0 else ""))
    in_progress = sum(sd.courses[c].credits for c in student.enrollments)
    if in_progress:
        after = max(0, rule.total - earned_total - in_progress)
        lines.append(
            f"- 이번 학기 수강 중: {in_progress}학점 (모두 이수하면 남은 학점은 총 {after}학점)"
        )
    return ["\n".join(lines)], []


HANDLERS: dict[str, Handler] = {
    "next_class": next_class,
    "day_classes": day_classes,
    "remaining_credits": remaining_credits,
}
