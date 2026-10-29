"""격리 메모리 테스트 전용 가상 학적 초기화. 운영 migration/seed 명령이 아니다.

DEC-020의 명시적 시드 방향은 유지하지만 공통 UUID 원장·migration 승인은 별개다.
기존 원격 자료에 legacy 테이블을 생성하거나 병합하지 않는다.
"""

import asyncio
from importlib.resources import as_file, files

from chatbot.app.data_loader import load_data, load_mock_data
from chatbot.app.db import DatabaseNotReady, init_db, make_engine
from chatbot.app.schemas import MockData

from app.core.config import Settings


def load_demo_mock() -> MockData:
    """챗봇 패키지의 가상 학생·강의·수강·시험·졸업 기준 (참조 무결성 검증 포함)."""
    with as_file(files("chatbot").joinpath("data")) as data_dir:
        return load_mock_data(data_dir / "mock", load_data(data_dir))


async def seed(url: str) -> bool:
    """폐기 가능한 canonical 메모리 DB에만 시드한다. 다른 대상은 연결 전에 거부한다."""
    if url != "sqlite+aiosqlite:///:memory:":
        raise DatabaseNotReady("가상 학적 초기화는 격리 SQLite 메모리 테스트에서만 허용됩니다.")
    engine = make_engine(url)
    try:
        return await init_db(engine, load_demo_mock())
    finally:
        await engine.dispose()


def main() -> None:
    settings = Settings()
    if settings.database_url is None:
        raise SystemExit("DIT_API_DATABASE_URL이 필요합니다")
    try:
        seeded = asyncio.run(seed(settings.database_url.get_secret_value()))
    except DatabaseNotReady:
        raise SystemExit(
            "원격 초기화는 차단되었습니다. 승인된 공통 원장 migration 절차가 필요합니다."
        ) from None
    print("가상 학적 데이터를 넣었습니다" if seeded else "이미 데이터가 있어 시드를 건너뛰었습니다")


if __name__ == "__main__":
    main()
