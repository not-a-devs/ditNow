from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.chatbot.assistant import Assistant, get_assistant
from app.schemas.auth import LoginData, LoginInput
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/auth", tags=["auth"])

# auto_error=False: 토큰 없는 교내 질문을 허용한다. /docs의 Authorize 버튼도 이 스킴으로 생긴다
bearer = HTTPBearer(auto_error=False, description="/api/v1/auth/login에서 받은 token")
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
AssistantDep = Annotated[Assistant, Depends(get_assistant)]


async def get_session(assistant: AssistantDep) -> AsyncIterator[AsyncSession]:
    async for db in assistant.session():
        yield db


async def get_optional_session(assistant: AssistantDep) -> AsyncIterator[AsyncSession | None]:
    """DB 설정이 없어도 비로그인 교내 질문은 답할 수 있게 한다."""
    if assistant.engine is None:
        yield None
        return
    async for db in assistant.session():
        yield db


Session = Annotated[AsyncSession, Depends(get_session)]
OptionalSession = Annotated[AsyncSession | None, Depends(get_optional_session)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=SuccessResponse[LoginData])
async def login(
    body: LoginInput, request: Request, assistant: AssistantDep, db: Session
) -> SuccessResponse[LoginData]:
    """학번과 초기 비밀번호로 로그인한다. 학생·학적은 모두 가상(DEMO) 데이터다."""
    assistant.check_rate_limit(client_ip(request))
    return SuccessResponse(data=await assistant.login(db, body.student_id, body.password))


@router.post("/logout", response_model=SuccessResponse[dict[str, str]])
async def logout(
    creds: Credentials, assistant: AssistantDep, db: Session
) -> SuccessResponse[dict[str, str]]:
    if creds:
        await assistant.logout(db, creds.credentials)
    return SuccessResponse(data={"status": "ok"})
