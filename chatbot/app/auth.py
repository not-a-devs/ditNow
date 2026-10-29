import hashlib
import hmac
import secrets
import time

from app.schemas import Student, StudentData

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


def authenticate(data: StudentData, student_id: str, password: str) -> Student | None:
    """학번·초기 비밀번호(주민등록번호 뒷자리)로 로그인한다."""
    student = data.students.get(student_id)
    if student is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return student if verify_password(password, student.password_hash) else None


class SessionStore:
    """로그인 토큰 → 학번. 카카오 로그인도 학생을 찾은 뒤 같은 issue()로 토큰을 발급한다."""

    # shortcut: 메모리 보관이라 서버 재시작 시 모두 로그아웃되고 단일 워커 전제, 운영 시 JWT·Redis로
    def __init__(self, ttl_sec: float = SESSION_TTL_SEC) -> None:
        self.ttl_sec = ttl_sec
        self._tokens: dict[str, tuple[str, float]] = {}

    def issue(self, student_id: str) -> str:
        """새 토큰을 발급한다."""
        token = secrets.token_urlsafe(32)
        self._tokens[token] = (student_id, time.monotonic() + self.ttl_sec)
        return token

    def resolve(self, token: str) -> str | None:
        """토큰의 학번을 돌려준다. 없거나 만료되면 None."""
        entry = self._tokens.get(token)
        if entry is None or entry[1] < time.monotonic():
            self._tokens.pop(token, None)
            return None
        return entry[0]

    def revoke(self, token: str) -> None:
        """토큰을 폐기한다 (로그아웃)."""
        self._tokens.pop(token, None)
