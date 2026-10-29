import json
import shutil
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import auth
from app.auth import (
    authenticate,
    hash_password,
    issue_token,
    resolve_token,
    revoke_token,
    verify_password,
)
from app.config import ROOT_DIR
from app.data_loader import DataError, load_data, load_mock_data
from app.models import AuthSessionRow
from app.schemas import CampusData
from tests.conftest import FIXTURES
from tests.test_api import client  # noqa: F401  (픽스처 재사용)


def test_password_hash_roundtrip() -> None:
    """해시는 평문을 담지 않고, 맞는 비밀번호만 통과한다."""
    stored = hash_password("3000001")
    assert "3000001" not in stored
    assert verify_password("3000001", stored)
    assert not verify_password("3000002", stored)
    assert not verify_password("3000001", "broken")


async def test_authenticate(db: AsyncSession) -> None:
    """학번·초기 비밀번호로 로그인한다."""
    assert (await authenticate(db, "20231001", "3000001")).name == "김동의"
    assert await authenticate(db, "20231001", "wrong") is None
    assert await authenticate(db, "99999999", "3000001") is None


async def test_token_lifecycle(db: AsyncSession) -> None:
    """발급 → 조회 → 폐기. DB에는 토큰 원문이 아닌 해시만 남는다."""
    token = await issue_token(db, "20231001")
    assert await resolve_token(db, token) == "20231001"
    assert await db.get(AuthSessionRow, token) is None  # 원문으로는 찾을 수 없다
    await revoke_token(db, token)
    assert await resolve_token(db, token) is None


async def test_expired_token(db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """만료된 토큰은 무효이고, 다음 발급 때 지워진다."""
    token = await issue_token(db, "20231001")
    later = auth.now_utc() + timedelta(seconds=auth.SESSION_TTL_SEC + 1)
    monkeypatch.setattr(auth, "now_utc", lambda: later)
    assert await resolve_token(db, token) is None
    await issue_token(db, "20231001")
    assert await db.get(AuthSessionRow, auth._token_hash(token)) is None


def test_real_mock_data_loads() -> None:
    """실제 data/mock 목업이 참조 검증을 통과한다."""
    campus = load_data(ROOT_DIR / "data")
    mock = load_mock_data(ROOT_DIR / "data" / "mock", campus)
    assert len(mock.students) == 3 and mock.enrollments


def test_mock_broken_enrollment(tmp_path: Path, campus_data: CampusData) -> None:
    """수강 이력이 없는 강의를 가리키면 에러."""
    for f in (FIXTURES / "mock").iterdir():
        shutil.copy(f, tmp_path / f.name)
    rows = json.loads((tmp_path / "enrollments.json").read_text(encoding="utf-8"))
    rows[0]["course_id"] = "NOPE"
    (tmp_path / "enrollments.json").write_text(json.dumps(rows, ensure_ascii=False))
    with pytest.raises(DataError, match="NOPE"):
        load_mock_data(tmp_path, campus_data)


def test_login_api(client: TestClient) -> None:  # noqa: F811
    """로그인 성공 시 토큰, 실패 시 401. 로그아웃하면 그 토큰은 401이 된다."""
    bad = client.post("/auth/login", json={"student_id": "20231001", "password": "x"})
    assert bad.status_code == 401
    res = client.post("/auth/login", json={"student_id": "20231001", "password": "3000001"})
    assert res.json()["name"] == "김동의"
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    assert client.post("/ask", json={"question": "학식"}, headers=headers).status_code == 200
    client.post("/auth/logout", headers=headers)
    assert client.post("/ask", json={"question": "학식"}, headers=headers).status_code == 401
