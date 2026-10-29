"""학번 로그인 (시연용 가상 학적 데이터)."""

from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel


class LoginInput(ApiModel):
    student_id: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=64)


class LoginData(ApiModel):
    token: str
    token_type: Literal["Bearer"] = "Bearer"
    student_id: str
    name: str
    record_source: Literal["DEMO"] = "DEMO"
