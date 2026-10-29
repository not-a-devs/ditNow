from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.data_loader import load_data, load_mock_data
from app.db import init_db, make_engine
from app.schemas import CampusData, MockData, Student, StudentData
from app.student_repo import load_student

FIXTURES = Path(__file__).parent / "fixtures"
SQLITE_MEMORY = "sqlite+aiosqlite:///:memory:"
SEMESTER = "2026-2"


@pytest.fixture(scope="session")
def campus_data() -> CampusData:
    """tests/fixtures의 작은 테스트 데이터."""
    return load_data(FIXTURES)


@pytest.fixture(scope="session")
def mock_data(campus_data: CampusData) -> MockData:
    """tests/fixtures/mock의 학생 목업 (김동의 20231001 / 비밀번호 3000001, 박졸업 20221003)."""
    return load_mock_data(FIXTURES / "mock", campus_data)


@pytest.fixture
async def db(mock_data: MockData) -> AsyncIterator[AsyncSession]:
    """목업을 시드한 SQLite 메모리 DB 세션 (테스트마다 새로)."""
    engine = make_engine(SQLITE_MEMORY)
    await init_db(engine, mock_data)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def students(db: AsyncSession) -> dict[str, tuple[Student, StudentData]]:
    """학번 → DB에서 읽은 (학생, 강의·졸업 기준)."""
    out = {}
    for sid in ("20231001", "20221003"):
        bundle = await load_student(db, sid, SEMESTER)
        assert bundle is not None
        out[sid] = bundle
    return out
