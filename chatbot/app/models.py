"""MariaDB 테이블 (SQLAlchemy ORM). 테스트에서는 같은 모델을 SQLite에 만든다."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """모든 테이블의 부모."""


class StudentRow(Base):
    """학적. 학번이 로그인 아이디."""

    __tablename__ = "students"

    student_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    dept_id: Mapped[str] = mapped_column(String(50))  # facilities.json의 학과 id
    grade: Mapped[int] = mapped_column(Integer)
    password_hash: Mapped[str] = mapped_column(String(200))
    kakao_id: Mapped[str | None] = mapped_column(String(64), unique=True, default=None)


class CourseRow(Base):
    """개설 강의."""

    __tablename__ = "courses"

    course_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    credits: Mapped[int] = mapped_column(Integer)
    professor: Mapped[str] = mapped_column(String(50))
    sessions: Mapped[list["CourseSessionRow"]] = relationship(
        order_by="CourseSessionRow.id", cascade="all, delete-orphan"
    )


class CourseSessionRow(Base):
    """강의 회차 (요일·시간·강의실)."""

    __tablename__ = "course_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.course_id", ondelete="CASCADE"))
    day: Mapped[str] = mapped_column(String(1))
    start: Mapped[str] = mapped_column(String(5))
    end: Mapped[str] = mapped_column(String(5))
    building_id: Mapped[str] = mapped_column(String(50))  # buildings.json의 id
    room: Mapped[str] = mapped_column(String(20))


class EnrollmentRow(Base):
    """수강 이력. 취득 학점은 저장하지 않고 이 표에서 계산한다."""

    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "course_id", "semester"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(
        ForeignKey("students.student_id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.course_id"))
    semester: Mapped[str] = mapped_column(String(6))  # 예: 2026-2
    category: Mapped[str] = mapped_column(String(10))  # 이수 구분: 전공·교양·일반
    grade: Mapped[str | None] = mapped_column(String(2), default=None)  # None이면 수강 중
    course: Mapped[CourseRow] = relationship()


class ExamRow(Base):
    """시험 일정 (중간·기말)."""

    __tablename__ = "exams"
    __table_args__ = (UniqueConstraint("course_id", "kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.course_id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(2))  # 중간 | 기말
    date: Mapped[date] = mapped_column(Date)
    start: Mapped[str] = mapped_column(String(5))
    end: Mapped[str] = mapped_column(String(5))
    building_id: Mapped[str] = mapped_column(String(50))
    room: Mapped[str] = mapped_column(String(20))


class GraduationRuleRow(Base):
    """학과별 졸업 총 학점."""

    __tablename__ = "graduation_rules"

    dept_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    total: Mapped[int] = mapped_column(Integer)
    categories: Mapped[list["GraduationCategoryRow"]] = relationship(
        order_by="GraduationCategoryRow.id", cascade="all, delete-orphan"
    )


class GraduationCategoryRow(Base):
    """이수 구분별 최소 학점 (전공 54 등)."""

    __tablename__ = "graduation_rule_categories"
    __table_args__ = (UniqueConstraint("dept_id", "category"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dept_id: Mapped[str] = mapped_column(ForeignKey("graduation_rules.dept_id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(10))
    min_credits: Mapped[int] = mapped_column(Integer)


class AuthSessionRow(Base):
    """로그인 세션. 토큰 원문이 아닌 해시만 저장해 DB가 유출돼도 토큰을 쓸 수 없다."""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_id: Mapped[str] = mapped_column(
        ForeignKey("students.student_id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime)  # UTC (timezone 없음)


class QuestionLogRow(Base):
    """질문 로그 (커버리지 개선용). 누가 물었는지(학번)는 남기지 않는다."""

    __tablename__ = "question_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)  # UTC
    question: Mapped[str] = mapped_column(String(200))
    rewritten_question: Mapped[str | None] = mapped_column(String(200), default=None)  # 후속 질문
    intent: Mapped[str] = mapped_column(String(30))
    classified_by: Mapped[str] = mapped_column(String(10))  # keyword | llm
    found: Mapped[bool] = mapped_column(Boolean)
    need_login: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[int] = mapped_column(Integer)
