from pathlib import Path

import pytest

from app.data_loader import load_data, load_student_data
from app.schemas import CampusData, StudentData

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def campus_data() -> CampusData:
    """tests/fixtures의 작은 테스트 데이터."""
    return load_data(FIXTURES)


@pytest.fixture(scope="session")
def student_data(campus_data: CampusData) -> StudentData:
    """tests/fixtures/mock의 학생 목업 (김동의 20231001 / 비밀번호 3000001, 박졸업 20221003)."""
    return load_student_data(FIXTURES / "mock", campus_data)
