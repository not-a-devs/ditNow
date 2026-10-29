"""DB 테이블을 만들고 data/mock 목업을 넣는다.

python scripts/seed_db.py           # 테이블 생성, 비어 있으면 시드
python scripts/seed_db.py --reset   # 모든 테이블을 지우고 다시 시드 (로그인 세션도 삭제)
"""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.data_loader import load_data, load_mock_data  # noqa: E402
from app.db import init_db, make_engine  # noqa: E402


async def main(reset: bool) -> None:
    """목업을 검증한 뒤 DB에 넣는다."""
    settings = get_settings()
    mock = load_mock_data(settings.mock_dir, load_data(settings.data_dir))
    engine = make_engine(settings.database_url)
    seeded = await init_db(engine, mock, reset=reset)
    await engine.dispose()
    if seeded:
        print(
            f"시드 완료: 학생 {len(mock.students)}명, 강의 {len(mock.courses)}개, "
            f"수강 이력 {len(mock.enrollments)}건"
        )
    else:
        print("이미 데이터가 있어 건너뜀 (다시 넣으려면 --reset)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="테이블을 지우고 다시 시드")
    asyncio.run(main(parser.parse_args().reset))
