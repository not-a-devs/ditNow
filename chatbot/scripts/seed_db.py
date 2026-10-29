"""폐기 가능한 SQLite 메모리 테스트에만 목업을 넣는다.

DATABASE_URL=sqlite+aiosqlite:///:memory: python scripts/seed_db.py --confirm-ephemeral-test
운영·기존 MariaDB 스키마 생성, reset, 사용자/세션 provisioning은 수행하지 않는다.
"""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.data_loader import load_data, load_mock_data  # noqa: E402
from app.db import DatabaseNotReady, init_db, make_engine  # noqa: E402


async def main() -> None:
    """명시한 메모리 테스트 원장에만 픽스처를 넣는다."""
    settings = get_settings()
    if settings.database_url != "sqlite+aiosqlite:///:memory:":
        raise DatabaseNotReady("이 명령은 SQLite 메모리 테스트에서만 실행할 수 있습니다.")
    mock = load_mock_data(settings.mock_dir, load_data(settings.data_dir))
    engine = make_engine(settings.database_url)
    try:
        await init_db(engine, mock)
        print(
            f"폐기 가능한 메모리 테스트: 학생 {len(mock.students)}명, 강의 {len(mock.courses)}개, "
            f"수강 이력 {len(mock.enrollments)}건"
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-ephemeral-test", action="store_true", help="폐기 가능한 메모리 테스트 실행 확인"
    )
    if not parser.parse_args().confirm_ephemeral_test:
        parser.error(
            "--confirm-ephemeral-test 확인이 필요합니다. 운영 초기화/reset은 지원하지 않습니다."
        )
    try:
        asyncio.run(main())
    except DatabaseNotReady as error:
        parser.exit(2, f"{error}\n")
