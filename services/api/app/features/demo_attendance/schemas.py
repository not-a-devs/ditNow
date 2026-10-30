"""DTOs for ``/me/demo-attendance``. Every payload is fixed synthetic DEMO content."""

from typing import Literal

from pydantic import AwareDatetime, Field

from app.schemas.common import ApiModel

DEMO_CODE = "123456"
CODE_PATTERN = r"^[0-9]{6}$"

DemoMode = Literal["DEMO"]
DemoStorage = Literal["PROCESS_MEMORY"]
DemoMethod = Literal["NUMERIC_CODE_SIMULATION"]

CARD_NOTICE = (
    "시연용 가상 카드입니다. "
    "실제 학생증·신분 증명·출입 인증으로 "
    "사용할 수 없으며 서버 재시작 시 초기화됩니다."
)
SESSION_NOTICE = (
    "가상 출석 연습입니다. 블루투스·QR·위치 확인을 하지 않으며 실제 출결 기록에 반영되지 않습니다."
)


class DemoCard(ApiModel):
    mode: DemoMode = "DEMO"
    storage: DemoStorage = "PROCESS_MEMORY"
    display_alias: str
    card_label: str
    valid_credential: Literal[False] = False
    qr_enabled: Literal[False] = False
    notice: str


class DemoSession(ApiModel):
    session_label: str
    method: DemoMethod = "NUMERIC_CODE_SIMULATION"
    simulation_code: str
    notice: str


class DemoCardView(ApiModel):
    card: DemoCard
    session: DemoSession


class CheckInRequest(ApiModel):
    code: str = Field(min_length=6, max_length=6, pattern=CODE_PATTERN)


class DemoAttendanceState(ApiModel):
    mode: DemoMode = "DEMO"
    storage: DemoStorage = "PROCESS_MEMORY"
    method: DemoMethod = "NUMERIC_CODE_SIMULATION"
    checked_in: bool
    checked_in_at: AwareDatetime | None = None


class CheckInResult(ApiModel):
    mode: DemoMode = "DEMO"
    storage: DemoStorage = "PROCESS_MEMORY"
    method: DemoMethod = "NUMERIC_CODE_SIMULATION"
    checked_in_at: AwareDatetime
    replayed: bool


def demo_card_view() -> DemoCardView:
    return DemoCardView(
        card=DemoCard(
            display_alias="DEMO 가상 학생",
            card_label="DEMO 모바일 학생증 (시뮬레이션)",
            notice=CARD_NOTICE,
        ),
        session=DemoSession(
            session_label="DEMO 가상 출석 세션",
            simulation_code=DEMO_CODE,
            notice=SESSION_NOTICE,
        ),
    )
