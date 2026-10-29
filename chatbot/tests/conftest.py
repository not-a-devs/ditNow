from pathlib import Path

import pytest

from app.data_loader import load_data
from app.schemas import CampusData

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def campus_data() -> CampusData:
    """tests/fixtures의 작은 테스트 데이터."""
    return load_data(FIXTURES)
