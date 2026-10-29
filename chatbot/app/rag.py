import logging
import re
import time
from datetime import datetime

from app.intents import CAMPUS, classify
from app.llm import ChatMessage, LLMClient, LLMError
from app.personal import HANDLERS, KST
from app.prompt import (
    LLM_FAILURE_ANSWER,
    LOGIN_REQUIRED_ANSWER,
    NOT_FOUND_ANSWER,
    NOT_FOUND_MARKER,
    SYSTEM_PROMPT,
    build_user_message,
)
from app.retriever.base import Retriever
from app.schemas import AskResponse, CampusData, LocationOut, Student, StudentData

logger = logging.getLogger(__name__)

_SOURCES_LINE = re.compile(r"\[근거:\s*([^\]]*)\]")
_BLOCK_ID = re.compile(r"^\[([^\]]+)\]")


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
    student_data: StudentData | None = None,
    student: Student | None = None,
    now: datetime | None = None,
) -> AskResponse:
    """질문 → 의도 분류 → (검색 | 개인 데이터 계산) → 프롬프트 → LLM → 근거 파싱."""
    start = time.perf_counter()
    intent = classify(question)

    def done(**kw: object) -> AskResponse:
        ms = int((time.perf_counter() - start) * 1000)
        return AskResponse(**kw, intent=intent, latency_ms=ms)

    if intent == CAMPUS:
        hits = retriever.search(question, top_k)
        if not hits:
            # 근거가 없으면 LLM을 부르지 않는다 (비용 절감 + 환각 방지)
            return done(answer=NOT_FOUND_ANSWER, found=False)
        blocks = [h.doc.to_context() for h in hits]
        personal_locations: list[LocationOut] = []
    elif student is None or student_data is None:
        return done(answer=LOGIN_REQUIRED_ANSWER, found=False, need_login=True)
    else:
        blocks, personal_locations = HANDLERS[intent](
            student, student_data, data, now or datetime.now(KST)
        )

    messages = [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=build_user_message(blocks, question, max_context_chars)),
    ]
    try:
        raw = await llm.chat(messages)
    except LLMError as e:
        logger.error("LLM 호출 실패: %s", e)
        return done(answer=LLM_FAILURE_ANSWER, found=True)

    allowed = {m.group(1) for b in blocks if (m := _BLOCK_ID.match(b))}
    answer, sources = parse_sources(raw, allowed)
    if not sources and NOT_FOUND_MARKER in answer:
        return done(answer=answer, found=False)
    if intent == CAMPUS:
        locations = find_locations(data, sources)
    else:
        locations = [loc for loc in personal_locations if loc.id in sources]
    return done(answer=answer, sources=sources, locations=locations, found=True)
