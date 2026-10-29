import logging

import pytest

from app.llm import ChatMessage, LLMClient, LLMError
from app.llm.fake_client import FakeLLMClient
from app.prompt import CLASSIFY_PROMPT, LLM_FAILURE_ANSWER, NOT_FOUND_ANSWER, build_user_message
from app.rag import answer_question, find_locations, parse_sources
from app.retriever.keyword import KeywordRetriever
from app.schemas import CampusData


class _FixedLLM(LLMClient):
    """정해진 답을 돌려주거나 에러를 던지는 테스트용 클라이언트."""

    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply

    async def chat(self, messages: list[ChatMessage], **_: object) -> str:
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture
def retriever(campus_data: CampusData) -> KeywordRetriever:
    return KeywordRetriever(list(campus_data.facilities.values()))


async def _ask(q: str, llm: LLMClient, retriever: KeywordRetriever, data: CampusData):
    return await answer_question(q, retriever=retriever, llm=llm, data=data)


async def test_found(retriever: KeywordRetriever, campus_data: CampusData) -> None:
    """검색된 문서가 근거로 나오고 본문에서 [근거:] 줄은 빠진다."""
    res = await _ask("컴소과 사무실 어디야", FakeLLMClient(), retriever, campus_data)
    assert res.found and res.sources == ["dept_cs"]
    assert "[근거" not in res.answer


async def test_no_hits_skips_llm(retriever: KeywordRetriever, campus_data: CampusData) -> None:
    """검색 결과가 없으면 답변 생성 LLM은 부르지 않고 고정 문구 (의도 분류 호출 1번만)."""
    llm = FakeLLMClient()
    res = await _ask("오늘 날씨 어때?", llm, retriever, campus_data)
    assert (res.answer, res.found) == (NOT_FOUND_ANSWER, False)
    assert [m[0].content for m in llm.calls] == [CLASSIFY_PROMPT]


async def test_llm_failure(retriever: KeywordRetriever, campus_data: CampusData) -> None:
    """LLM이 최종 실패하면 안내 문구를 돌려준다."""
    res = await _ask("학식", _FixedLLM(LLMError("x")), retriever, campus_data)
    assert res.answer == LLM_FAILURE_ANSWER and res.sources == []


async def test_llm_failure_logs_error_type_only(
    retriever: KeywordRetriever, campus_data: CampusData, caplog: pytest.LogCaptureFixture
) -> None:
    """공급자 오류 문자열(키 일부·요청 조각)은 로그에 남기지 않고 예외 종류만 남긴다."""
    error = LLMError("sentinel-key-hint sk-sentinel 학식 질문")
    with caplog.at_level(logging.ERROR, logger="app.rag"):
        res = await _ask("학식", _FixedLLM(error), retriever, campus_data)
    assert res.answer == LLM_FAILURE_ANSWER
    assert "LLMError" in caplog.text
    assert "sentinel" not in caplog.text and "학식 질문" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


async def test_llm_says_not_registered(
    retriever: KeywordRetriever, campus_data: CampusData
) -> None:
    """검색은 됐지만 LLM이 '등록되어 있지 않아요'라고 하면 found=False."""
    llm = _FixedLLM("해당 정보는 아직 등록되어 있지 않아요.")
    res = await _ask("학식 메뉴 뭐야", llm, retriever, campus_data)
    assert res.found is False


async def test_refusal_with_sources_is_not_found(
    retriever: KeywordRetriever, campus_data: CampusData
) -> None:
    """거절하면서 [근거]를 붙여도 found=False (실제 LLM 평가에서 발견)."""
    llm = _FixedLLM("해당 정보는 아직 등록되어 있지 않아요.\n[근거: fac_cafeteria]")
    res = await _ask("학식 메뉴 뭐야", llm, retriever, campus_data)
    assert res.found is False


async def test_partial_answer_is_found(
    retriever: KeywordRetriever, campus_data: CampusData
) -> None:
    """아는 부분을 답하고 일부만 등록되어 있지 않다고 하면 정상 답변."""
    llm = _FixedLLM(
        "학생식당은 13:50까지 운영해요. 메뉴는 아직 등록되어 있지 않아요.\n[근거: fac_cafeteria]"
    )
    res = await _ask("학식 몇시까지 하고 메뉴 뭐야", llm, retriever, campus_data)
    assert res.found is True and res.sources == ["fac_cafeteria"]


def test_parse_sources_strips_ids_in_body() -> None:
    """본문의 '(CS201)'·'[CS201]' 같은 내부 id 표기는 지운다 (실제 LLM 평가에서 발견)."""
    raw = "자료구조(CS201), 웹프로그래밍 [CS205]입니다. CS 전공이에요.\n[근거: CS201, CS205]"
    answer, ids = parse_sources(raw, {"CS201", "CS205"})
    assert (answer, ids) == ("자료구조, 웹프로그래밍입니다. CS 전공이에요.", ["CS201", "CS205"])
    mixed, _ = parse_sources(
        "데이터베이스(CS210, 담당 한교수)와 (3학점, CS205) 수업", {"CS210", "CS205"}
    )
    assert mixed == "데이터베이스(담당 한교수)와 (3학점) 수업"
    bare, _ = parse_sources("금요일에 GE101 수업이 있어요. GE1010호 아님", {"GE101"})
    assert bare == "금요일에 수업이 있어요. GE1010호 아님"
    meta, _ = parse_sources(
        "총 4과목이에요. 근거 문서의 id는 CS201, GE101이에요.\n[근거: CS201, GE101]",
        {"CS201", "GE101"},
    )
    assert meta == "총 4과목이에요."
    plain, ids = parse_sources("4과목이에요.\n근거: CS201, CS205", {"CS201", "CS205"})
    assert (plain, ids) == ("4과목이에요.", ["CS201", "CS205"])  # 대괄호 없는 근거 줄


def test_parse_sources_drops_unknown_ids() -> None:
    """검색 결과에 없던 id(환각)는 버린다."""
    answer, ids = parse_sources("답입니다.\n[근거: a, ghost, a, b]", {"a", "b"})
    assert (answer, ids) == ("답입니다.", ["a", "b"])


def test_locations_need_coordinates(campus_data: CampusData) -> None:
    """건물 좌표가 있을 때만 locations에 들어간다."""
    assert find_locations(campus_data, ["dept_cs"]) == []
    data = campus_data.model_copy(deep=True)
    data.buildings["mirae"].lat, data.buildings["mirae"].lng = 35.1, 129.0
    [loc] = find_locations(data, ["dept_cs"])
    assert (loc.building, loc.lat) == ("미래관", 35.1)


def test_context_limit_keeps_top_hit(retriever: KeywordRetriever) -> None:
    """컨텍스트가 길면 점수 낮은 문서부터 빠지고, 최상위 문서는 항상 남는다."""
    hits = retriever.search("기숙사 편의점 정보관 전기과")
    assert len(hits) > 1
    msg = build_user_message([h.doc.to_context() for h in hits], "q", max_chars=1)
    assert f"[{hits[0].doc.id}]" in msg and f"[{hits[1].doc.id}]" not in msg
