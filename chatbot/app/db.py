"""런타임 DB 연결·읽기 전용 준비 검사와 격리 테스트 초기화."""

from typing import Protocol

from pydantic import SecretStr
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import SQLAlchemyError
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


class ApprovedEngineFactory(Protocol):
    """공통 소유자가 TLS/timeout/최소 권한을 검토한 생성자만 주입한다."""

    def __call__(self, database_url: SecretStr) -> AsyncEngine: ...


def make_engine(
    url: str | SecretStr, *, approved_factory: ApprovedEngineFactory | None = None
) -> AsyncEngine:
    """메모리 테스트 외 연결은 승인된 공통 DB 생성자 없이는 차단한다."""
    secret = url if isinstance(url, SecretStr) else SecretStr(url)
    raw = secret.get_secret_value()
    if not raw:
        raise ValueError("DATABASE_URL이 비어 있습니다 (.env 확인, 예: .env.example)")
    if raw == "sqlite+aiosqlite:///:memory:":
        return create_async_engine(raw, poolclass=StaticPool, hide_parameters=True)
    if approved_factory is None:
        raise DatabaseNotReady("메모리 테스트 외 DB는 승인된 공통 연결 정책이 필요합니다.")
    try:
        engine = approved_factory(secret)
        if not engine.sync_engine.hide_parameters:
            raise DatabaseNotReady("DB SQL 파라미터 숨김 설정이 필요합니다.")
        return engine
    except Exception:
        raise DatabaseNotReady("DB 연결 정책 또는 설정을 확인하세요.") from None


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
    url = engine.url
    if (
        url.drivername != "sqlite+aiosqlite"
        or url.database != ":memory:"
        or bool(url.query)
        or any(part is not None for part in (url.username, url.password, url.host, url.port))
    ):
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
