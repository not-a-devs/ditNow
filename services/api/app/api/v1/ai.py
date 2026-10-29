from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.v1.auth import AssistantDep, Credentials, OptionalSession, client_ip
from app.core.errors import ApiError
from app.integrations.chatbot.campus import CampusSearch, get_campus_search
from app.schemas.ai import AskData, AskInput, CampusSearchData
from app.schemas.common import ErrorCode, SuccessResponse

router = APIRouter(prefix="/ai", tags=["campus-search"])


@router.get("/campus/search", response_model=SuccessResponse[CampusSearchData])
def search_campus(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    search: Annotated[CampusSearch, Depends(get_campus_search)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> SuccessResponse[CampusSearchData]:
    """공개 시설 스냅샷 검색. LLM 생성·개인정보 질의·별도 로그인은 제공하지 않는다."""
    if not q.strip() or not any(character.isalnum() for character in q):
        raise ApiError(ErrorCode.VALIDATION)
    return SuccessResponse(data=search.search(q.strip(), limit))


@router.post("/ask", response_model=SuccessResponse[AskData])
async def ask(
    body: AskInput,
    request: Request,
    creds: Credentials,
    assistant: AssistantDep,
    db: OptionalSession,
) -> SuccessResponse[AskData]:
    """자연어 질문에 교내 데이터·(로그인 시) 본인 가상 학적을 근거로 LLM이 답한다.

    history를 보내면 '거기 몇 시까지 해?' 같은 후속 질문을 완전한 질문으로 바꿔 처리한다.
    """
    student_id = await assistant.student_id(db, creds.credentials if creds else None)
    assistant.check_rate_limit(client_ip(request))
    return SuccessResponse(data=await assistant.ask(body, db, student_id))
