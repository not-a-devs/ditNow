"""로그인한 학생의 개인 질문 처리기.

숫자·시간 계산은 여기서 코드로 끝내고, LLM에는 확정된 사실만 <context>로 넘긴다.
"""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

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
Handler = Callable[[Student, StudentData, CampusData, datetime], Result]


def _classes(student: Student, sd: StudentData) -> list[tuple[Course, ClassSession]]:
    """학생이 이번 학기 듣는 모든 강의 회차."""
    return [(c, s) for c in (sd.courses[i] for i in student.enrollments) for s in c.sessions]


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


def next_class(student: Student, sd: StudentData, campus: CampusData, now: datetime) -> Result:
    """지금 이후 가장 먼저 시작하는 수업 (일주일 뒤 같은 요일까지 탐색)."""
    classes = _classes(student, sd)
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


def today_classes(student: Student, sd: StudentData, campus: CampusData, now: datetime) -> Result:
    """오늘 요일의 수업 전체."""
    day = WEEKDAYS[now.weekday()]
    todays = sorted(
        (cs for cs in _classes(student, sd) if cs[1].day == day), key=lambda cs: cs[1].start
    )
    if not todays:
        return [f"[my_timetable] 오늘({day}요일)은 {student.name} 학생의 수업이 없습니다."], []
    blocks = [_describe(c, s, campus, f"오늘({day}요일) 수업") for c, s in todays]
    return blocks, [loc for c, s in todays for loc in _location(c, s, campus)]


def remaining_credits(
    student: Student, sd: StudentData, campus: CampusData, now: datetime
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
    "today_classes": today_classes,
    "remaining_credits": remaining_credits,
}
