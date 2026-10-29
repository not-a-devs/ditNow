import logging
import re
import time
from datetime import datetime

from .intents import CAMPUS, Intent, route
from .llm import ChatMessage, LLMClient, LLMError
from .personal import HANDLERS, KST, PersonalQuery
from .prompt import (
    LLM_FAILURE_ANSWER,
    LOGIN_REQUIRED_ANSWER,
    NOT_FOUND_ANSWER,
    NOT_FOUND_MARKER,
    SYSTEM_PROMPT,
    build_user_message,
)
from .retriever.base import Retriever
from .schemas import AskResponse, CampusData, LocationOut, Student, StudentData

logger = logging.getLogger(__name__)

# '[근거: a, b]'. 대괄호 없이 '근거: a, b'로 쓰는 경우도 있어 괄호는 선택
_SOURCES_LINE = re.compile(r"\[?근거:\s*([^\]\n]*)\]?")
_BLOCK_ID = re.compile(r"^\[([^\]]+)\]")
# 최신 모델은 답하기 전 추론에도 토큰을 써서, 시험 4과목 나열 같은 답이 600에서 잘렸다
ANSWER_MAX_TOKENS = 1024


def parse_sources(raw: str, allowed: set[str]) -> tuple[str, list[str]]:
    """답변에서 [근거: ...]를 떼어 내고, 검색 결과에 있던 id만 순서대로 남긴다.

    모델이 본문에 '자료구조(CS201)'처럼 내부 id를 따라 쓰는 경우가 있어 '(id)'·'[id]'도 지운다.
    """
    ids: list[str] = []
    for match in _SOURCES_LINE.finditer(raw):
        for part in match.group(1).split(","):
            doc_id = part.strip()
            if doc_id in allowed and doc_id not in ids:
                ids.append(doc_id)
    answer = _SOURCES_LINE.sub("", raw)
    # '근거 문서의 id는 CS201…이에요'처럼 근거를 본문 문장으로 쓰면 그 문장을 뺀다
    answer = "\n".join(
        " ".join(s for s in re.split(r"(?<=[.!?])\s+", line) if "근거" not in s)
        for line in answer.splitlines()
    )
    if allowed:
        names = "|".join(re.escape(i) for i in sorted(allowed, key=len, reverse=True))
        answer = re.sub(rf"\s*[(\[](?:{names})[)\]]", "", answer)  # '자료구조(CS201)'
        answer = re.sub(rf"(?<=[(\[])(?:{names}),\s*", "", answer)  # '(CS210, 담당 …)'
        answer = re.sub(rf",\s*(?:{names})(?=[)\]])", "", answer)  # '(담당 …, CS210)'
        answer = re.sub(rf"(?<!\w)(?:{names})(?!\w)\s?", "", answer)  # '금요일에 GE101 수업'
    return answer.strip(), ids


def _is_refusal(answer: str, sources: list[str]) -> bool:
    """'등록되어 있지 않아요'만 말한 답인지. 일부만 모른다는 여러 문장 답변은 정상 답변이다."""
    if NOT_FOUND_MARKER not in answer:
        return False
    sentences = [s for s in re.split(r"[.!?]\s*", answer.strip()) if s]
    return not sources or len(sentences) == 1


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
    intent: Intent | None = None,
) -> AskResponse:
    """질문 → 의도 분류 → (검색 | 개인 데이터 계산) → 프롬프트 → LLM → 근거 파싱.

    intent를 주면 분류를 건너뛴다 (/ask가 학생 데이터를 읽을지 정하려고 먼저 분류할 때).
    """
    start = time.perf_counter()
    intent = intent or await route(question, retriever, llm)

    def done(**kw: object) -> AskResponse:
        ms = int((time.perf_counter() - start) * 1000)
        return AskResponse(**kw, intent=intent.name, classified_by=intent.by, latency_ms=ms)

    if intent.name == CAMPUS:
        hits = retriever.search(question, top_k)
        if not hits:
            # 근거가 없으면 LLM을 부르지 않는다 (비용 절감 + 환각 방지)
            return done(answer=NOT_FOUND_ANSWER, found=False)
        blocks = [h.doc.to_context() for h in hits]
        personal_locations: list[LocationOut] = []
    elif student is None or student_data is None:
        return done(answer=LOGIN_REQUIRED_ANSWER, found=False, need_login=True)
    else:
        query = PersonalQuery(question, now or datetime.now(KST), intent.day)
        blocks, personal_locations = HANDLERS[intent.name](student, student_data, data, query)

    messages = [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=build_user_message(blocks, question, max_context_chars)),
    ]
    try:
        raw = await llm.chat(messages, max_tokens=ANSWER_MAX_TOKENS)
    except LLMError as e:
        # 공급자 오류 문자열에 키 일부·요청 조각이 섞일 수 있어 예외 종류만 남긴다
        logger.error("LLM 호출 실패: %s", type(e).__name__)
        return done(answer=LLM_FAILURE_ANSWER, found=True)

    allowed = {m.group(1) for b in blocks if (m := _BLOCK_ID.match(b))}
    answer, sources = parse_sources(raw, allowed)
    if _is_refusal(answer, sources):
        # 거절하면서 [근거]를 붙이는 모델도 있어, 근거 유무와 상관없이 거절로 본다
        return done(answer=answer, found=False)
    if intent.name == CAMPUS:
        locations = find_locations(data, sources)
    else:
        locations = [loc for loc in personal_locations if loc.id in sources]
    return done(answer=answer, sources=sources, locations=locations, found=True)
