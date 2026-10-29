"""DB 연결·테이블 생성·목업 시드."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import (
    Base,
    CourseRow,
    CourseSessionRow,
    EnrollmentRow,
    ExamRow,
    GraduationCategoryRow,
    GraduationRuleRow,
    StudentRow,
)
from app.schemas import MockData


def make_engine(url: str) -> AsyncEngine:
    """DATABASE_URL로 비동기 엔진을 만든다."""
    if not url:
        raise ValueError("DATABASE_URL이 비어 있습니다 (.env 확인, 예: .env.example)")
    if url.startswith("sqlite") and ":memory:" in url:
        # 메모리 SQLite는 연결마다 DB가 따로 생기므로 연결 하나를 공유한다 (테스트·평가용)
        return create_async_engine(url, poolclass=StaticPool)
    # MariaDB는 유휴 연결을 끊으므로 사용 전 확인하고 1시간마다 새로 맺는다
    return create_async_engine(url, pool_pre_ping=True, pool_recycle=3600)


async def init_db(engine: AsyncEngine, mock: MockData, *, reset: bool = False) -> bool:
    """테이블을 만들고, 학생이 한 명도 없으면 목업을 넣는다. 시드했으면 True."""
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
