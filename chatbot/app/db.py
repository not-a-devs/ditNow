"""런타임 DB 연결·읽기 전용 준비 검사와 격리 테스트 초기화."""

from sqlalchemy import func, inspect, select
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from .models import (
    Base,
    CourseRow,
    CourseSessionRow,
    EnrollmentRow,
    ExamRow,
    GraduationCategoryRow,
    GraduationRuleRow,
    StudentRow,
)
from .schemas import MockData


class DatabaseNotReady(RuntimeError):
    """접속 정보나 SQL 원문을 포함하지 않는 준비 실패."""


def make_engine(url: str) -> AsyncEngine:
    """DATABASE_URL로 비동기 엔진을 만든다."""
    if not url:
        raise ValueError("DATABASE_URL이 비어 있습니다 (.env 확인, 예: .env.example)")
    try:
        if url.startswith("sqlite") and ":memory:" in url:
            return create_async_engine(url, poolclass=StaticPool)
        return create_async_engine(url, pool_pre_ping=True, pool_recycle=3600)
    except (ArgumentError, ValueError):
        raise DatabaseNotReady("DB 연결 설정을 확인하세요.") from None


async def require_existing_schema(engine: AsyncEngine) -> None:
    """필수 테이블 존재만 검사하며 DDL·시드·사용자 생성은 수행하지 않는다."""
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda conn: set(inspect(conn).get_table_names()))
        if not set(Base.metadata.tables).issubset(tables):
            raise DatabaseNotReady(
                "필수 DB 스키마가 준비되지 않았습니다. 승인된 변경이 필요합니다."
            )
    except SQLAlchemyError:
        raise DatabaseNotReady("DB 접근 또는 스키마 준비 상태를 확인하세요.") from None


async def init_db(engine: AsyncEngine, mock: MockData, *, reset: bool = False) -> bool:
    """폐기 가능한 SQLite 메모리 테스트에서만 테이블과 픽스처를 만든다."""
    if engine.url.get_backend_name() != "sqlite" or engine.url.database != ":memory:":
        raise DatabaseNotReady("초기화와 reset은 SQLite 메모리 테스트에서만 허용됩니다.")
    async with engine.begin() as conn:
        if reset:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(engine)
    async with sessionmaker() as db:
        if await db.scalar(select(func.count()).select_from(StudentRow)):
            return False
        db.add_all(StudentRow(**s.model_dump()) for s in mock.students.values())
        db.add_all(
            CourseRow(
                **c.model_dump(exclude={"sessions"}),
                sessions=[CourseSessionRow(**s.model_dump()) for s in c.sessions],
            )
            for c in mock.courses.values()
        )
        db.add_all(
            GraduationRuleRow(
                dept_id=r.dept_id,
                total=r.total,
                categories=[
                    GraduationCategoryRow(category=k, min_credits=v)
                    for k, v in r.by_category.items()
                ],
            )
            for r in mock.rules.values()
        )
        await db.flush()  # 학생·강의가 먼저 들어가야 수강 이력의 외래키가 맞는다
        db.add_all(EnrollmentRow(**e.model_dump()) for e in mock.enrollments)
        db.add_all(ExamRow(**x.model_dump()) for x in mock.exams)
        await db.commit()
    return True
