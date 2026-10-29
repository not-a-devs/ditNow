"""학번 로그인·개인 질문용 테이블을 만들고 가상 학적 데이터를 넣는다 (DB가 비어 있을 때만).

서버 시작 시 자동 실행하지 않는다 (DEC-019). 테이블을 만들 수 있는 migration 계정으로 실행한다.

    export DIT_API_ENVIRONMENT=development
    export DIT_API_DATABASE_URL='mysql+aiomysql://ditnow_migrator:<pw>@<host>:3307/ditnow'
    uv run --locked python -m app.seed_demo
"""

import asyncio
from importlib.resources import as_file, files

from chatbot.app.data_loader import load_data, load_mock_data
from chatbot.app.db import init_db, make_engine
from chatbot.app.schemas import MockData

from app.core.config import Settings


def load_demo_mock() -> MockData:
    """챗봇 패키지의 가상 학생·강의·수강·시험·졸업 기준 (참조 무결성 검증 포함)."""
    with as_file(files("chatbot").joinpath("data")) as data_dir:
        return load_mock_data(data_dir / "mock", load_data(data_dir))


async def seed(url: str) -> bool:
    """테이블을 만들고, 학생이 없으면 시드한다. 시드했으면 True."""
    engine = make_engine(url)
    try:
        return await init_db(engine, load_demo_mock())
    finally:
        await engine.dispose()


def main() -> None:
    settings = Settings()
    if settings.database_url is None:
        raise SystemExit("DIT_API_DATABASE_URL이 필요합니다")
    seeded = asyncio.run(seed(settings.database_url.get_secret_value()))
    print("가상 학적 데이터를 넣었습니다" if seeded else "이미 데이터가 있어 시드를 건너뛰었습니다")


if __name__ == "__main__":
    main()
