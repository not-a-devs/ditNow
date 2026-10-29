import logging
import re
import time

from app.llm import ChatMessage, LLMClient, LLMError
from app.prompt import (
    LLM_FAILURE_ANSWER,
    NOT_FOUND_ANSWER,
    NOT_FOUND_MARKER,
    SYSTEM_PROMPT,
    build_user_message,
)
from app.retriever.base import Retriever
from app.schemas import AskResponse, CampusData, LocationOut

logger = logging.getLogger(__name__)

_SOURCES_LINE = re.compile(r"\[근거:\s*([^\]]*)\]")


def parse_sources(raw: str, allowed: set[str]) -> tuple[str, list[str]]:
    """답변에서 [근거: ...]를 떼어 내고, 검색 결과에 있던 id만 순서대로 남긴다."""
    ids: list[str] = []
    for match in _SOURCES_LINE.finditer(raw):
        for part in match.group(1).split(","):
            doc_id = part.strip()
            if doc_id in allowed and doc_id not in ids:
                ids.append(doc_id)
    return _SOURCES_LINE.sub("", raw).strip(), ids


def find_locations(data: CampusData, source_ids: list[str]) -> list[LocationOut]:
    """근거 시설 중 건물 좌표가 있는 것만 지도용으로 모은다."""
    out: list[LocationOut] = []
    for doc_id in source_ids:
        fac = data.facilities[doc_id]
        bld = data.buildings.get(fac.building_id or "")
        if bld and bld.lat is not None and bld.lng is not None:
            out.append(
                LocationOut(id=fac.id, name=fac.name, building=bld.name, lat=bld.lat, lng=bld.lng)
            )
    return out


async def answer_question(
    question: str,
    *,
    retriever: Retriever,
    llm: LLMClient,
    data: CampusData,
    top_k: int = 5,
    max_context_chars: int = 3000,
) -> AskResponse:
    """질문 → 검색 → 프롬프트 → LLM → 근거 파싱까지 수행한다."""
    start = time.perf_counter()

    def done(**kw: object) -> AskResponse:
        return AskResponse(**kw, latency_ms=int((time.perf_counter() - start) * 1000))

    hits = retriever.search(question, top_k)
    if not hits:
        # 근거가 없으면 LLM을 부르지 않는다 (비용 절감 + 환각 방지)
        return done(answer=NOT_FOUND_ANSWER, found=False)

    messages = [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=build_user_message(hits, question, max_context_chars)),
    ]
    try:
        raw = await llm.chat(messages)
    except LLMError as e:
        logger.error("LLM 호출 실패: %s", e)
        return done(answer=LLM_FAILURE_ANSWER, found=True)

    answer, sources = parse_sources(raw, {h.doc.id for h in hits})
    if not sources and NOT_FOUND_MARKER in answer:
        return done(answer=answer, found=False)
    return done(answer=answer, sources=sources, locations=find_locations(data, sources), found=True)
