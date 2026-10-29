import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth import SessionStore, authenticate, hash_password, verify_password
from app.config import ROOT_DIR
from app.data_loader import DataError, load_data, load_student_data
from app.schemas import CampusData, StudentData
from tests.conftest import FIXTURES
from tests.test_api import client  # noqa: F401  (픽스처 재사용)


def test_password_hash_roundtrip() -> None:
    """해시는 평문을 담지 않고, 맞는 비밀번호만 통과한다."""
    stored = hash_password("3000001")
    assert "3000001" not in stored
    assert verify_password("3000001", stored)
    assert not verify_password("3000002", stored)
    assert not verify_password("3000001", "broken")


def test_authenticate(student_data: StudentData) -> None:
    """학번·초기 비밀번호로 로그인한다."""
    assert authenticate(student_data, "20231001", "3000001").name == "김동의"
    assert authenticate(student_data, "20231001", "wrong") is None
    assert authenticate(student_data, "99999999", "3000001") is None


def test_session_expiry() -> None:
    """만료되거나 폐기된 토큰은 무효."""
    store = SessionStore(ttl_sec=60)
    token = store.issue("20231001")
    assert store.resolve(token) == "20231001"
    store.revoke(token)
    assert store.resolve(token) is None
    expired = SessionStore(ttl_sec=-1)
    assert expired.resolve(expired.issue("x")) is None


def test_real_mock_data_loads() -> None:
    """실제 data/mock 목업이 참조 검증을 통과한다."""
    campus = load_data(ROOT_DIR / "data")
    assert len(load_student_data(ROOT_DIR / "data" / "mock", campus).students) == 3


def test_mock_broken_course_ref(tmp_path: Path, campus_data: CampusData) -> None:
    """수강 목록이 없는 강의를 가리키면 에러."""
    for f in (FIXTURES / "mock").iterdir():
        shutil.copy(f, tmp_path / f.name)
    students = json.loads((tmp_path / "students.json").read_text(encoding="utf-8"))
    students[0]["enrollments"].append("NOPE")
    (tmp_path / "students.json").write_text(json.dumps(students, ensure_ascii=False))
    with pytest.raises(DataError, match="NOPE"):
        load_student_data(tmp_path, campus_data)


def test_login_api(client: TestClient) -> None:  # noqa: F811
    """로그인 성공 시 토큰, 실패 시 401. 로그아웃하면 토큰이 무효가 된다."""
    bad = client.post("/auth/login", json={"student_id": "20231001", "password": "x"})
    assert bad.status_code == 401
    res = client.post("/auth/login", json={"student_id": "20231001", "password": "3000001"})
    assert res.json()["name"] == "김동의"
    token = res.json()["token"]
    client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert client.app.state.sessions.resolve(token) is None
