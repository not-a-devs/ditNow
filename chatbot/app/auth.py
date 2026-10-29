import asyncio
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthSessionRow, StudentRow

ITERATIONS = 100_000
SESSION_TTL_SEC = 12 * 3600


def hash_password(password: str, salt: bytes | None = None) -> str:
    """비밀번호를 PBKDF2-SHA256으로 해시한다. 평문은 어디에도 저장하지 않는다."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """해시와 비밀번호가 일치하는지 상수 시간으로 비교한다."""
    try:
        _, iterations, salt, digest = stored.split("$")
        calc = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
        )
    except ValueError:
        return False
    return hmac.compare_digest(calc.hex(), digest)


# 없는 학번에도 같은 시간만큼 해시를 계산해 응답 시간으로 학번 존재 여부가 드러나지 않게 한다
_DUMMY_HASH = hash_password("dummy")


def now_utc() -> datetime:
    """DB에 저장하는 UTC 시각 (timezone 정보 없이)."""
    return datetime.now(UTC).replace(tzinfo=None)


def _token_hash(token: str) -> str:
    """토큰 원문 대신 저장할 해시."""
    return hashlib.sha256(token.encode()).hexdigest()


async def authenticate(db: AsyncSession, student_id: str, password: str) -> StudentRow | None:
    """학번·초기 비밀번호(주민등록번호 뒷자리)로 로그인한다."""
    row = await db.get(StudentRow, student_id)
    stored = row.password_hash if row else _DUMMY_HASH
    # PBKDF2는 수십 ms 걸리는 CPU 작업이라 이벤트 루프를 막지 않게 스레드에서 돌린다
    ok = await asyncio.to_thread(verify_password, password, stored)
    return row if row and ok else None


async def issue_token(db: AsyncSession, student_id: str) -> str:
    """새 토큰을 발급해 DB에 저장한다. 카카오 로그인도 학생을 찾은 뒤 이 함수를 쓴다."""
    token = secrets.token_urlsafe(32)
    await db.execute(delete(AuthSessionRow).where(AuthSessionRow.expires_at < now_utc()))
    db.add(
        AuthSessionRow(
            token_hash=_token_hash(token),
            student_id=student_id,
            expires_at=now_utc() + timedelta(seconds=SESSION_TTL_SEC),
        )
    )
    await db.commit()
    return token


async def resolve_token(db: AsyncSession, token: str) -> str | None:
    """토큰의 학번을 돌려준다. 없거나 만료되면 None."""
    row = await db.get(AuthSessionRow, _token_hash(token))
    if row is None or row.expires_at < now_utc():
        return None
    return row.student_id


async def revoke_token(db: AsyncSession, token: str) -> None:
    """토큰을 폐기한다 (로그아웃)."""
    await db.execute(delete(AuthSessionRow).where(AuthSessionRow.token_hash == _token_hash(token)))
    await db.commit()
