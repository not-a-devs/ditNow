from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.errors import ApiError
from app.integrations.chatbot.campus import CampusSearch, get_campus_search
from app.schemas.ai import CampusSearchData
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
