"""DB에서 학생 한 명의 정보를 읽어 처리기용 모델로 만든다."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import CourseRow, EnrollmentRow, GraduationRuleRow, StudentRow
from app.schemas import ClassSession, Course, GraduationRule, Student, StudentData

FAIL_GRADE = "F"


async def load_student(
    db: AsyncSession, student_id: str, semester: str
) -> tuple[Student, StudentData] | None:
    """학적·수강 이력·졸업 기준을 읽고 취득 학점을 계산한다. 없는 학번이면 None."""
    row = await db.get(StudentRow, student_id)
    if row is None:
        return None
    enrollments = (
        await db.scalars(
            select(EnrollmentRow)
            .where(EnrollmentRow.student_id == student_id)
            .options(selectinload(EnrollmentRow.course).selectinload(CourseRow.sessions))
            .order_by(EnrollmentRow.id)
        )
    ).all()
    rule = await db.get(
        GraduationRuleRow, row.dept_id, options=[selectinload(GraduationRuleRow.categories)]
    )
    if rule is None:
        raise LookupError(f"{row.dept_id}의 졸업 기준이 DB에 없습니다")

    # shortcut: 통과한 과목을 재수강하면 학점이 두 번 더해진다,
    # 실제 학사 데이터 연동 시 과목별 최신 성적만 집계
    earned: dict[str, int] = {}
    for e in enrollments:
        if e.grade is not None and e.grade != FAIL_GRADE:
            earned[e.category] = earned.get(e.category, 0) + e.course.credits
    current = [e.course for e in enrollments if e.semester == semester]

    student = Student(
        student_id=row.student_id,
        name=row.name,
        dept_id=row.dept_id,
        grade=row.grade,
        earned_credits=earned,
        enrollments=[c.course_id for c in current],
    )
    data = StudentData(
        courses={c.course_id: _course(c) for c in current},
        rules={
            rule.dept_id: GraduationRule(
                dept_id=rule.dept_id,
                total=rule.total,
                by_category={c.category: c.min_credits for c in rule.categories},
            )
        },
    )
    return student, data


def _course(c: CourseRow) -> Course:
    """ORM 강의를 처리기용 모델로 바꾼다."""
    return Course(
        course_id=c.course_id,
        name=c.name,
        credits=c.credits,
        professor=c.professor,
        sessions=[
            ClassSession(
                day=s.day, start=s.start, end=s.end, building_id=s.building_id, room=s.room
            )
            for s in c.sessions
        ],
    )
