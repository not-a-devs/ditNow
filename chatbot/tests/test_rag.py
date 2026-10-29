import pytest

from app.llm import ChatMessage, LLMClient, LLMError
from app.llm.fake_client import FakeLLMClient
from app.prompt import LLM_FAILURE_ANSWER, NOT_FOUND_ANSWER, build_user_message
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
    """검색 결과가 없으면 LLM을 부르지 않고 고정 문구."""
    llm = FakeLLMClient()
    res = await _ask("오늘 날씨 어때?", llm, retriever, campus_data)
    assert (res.answer, res.found, llm.calls) == (NOT_FOUND_ANSWER, False, [])


async def test_llm_failure(retriever: KeywordRetriever, campus_data: CampusData) -> None:
    """LLM이 최종 실패하면 안내 문구를 돌려준다."""
    res = await _ask("학식", _FixedLLM(LLMError("x")), retriever, campus_data)
    assert res.answer == LLM_FAILURE_ANSWER and res.sources == []


async def test_llm_says_not_registered(
    retriever: KeywordRetriever, campus_data: CampusData
) -> None:
    """검색은 됐지만 LLM이 '등록되어 있지 않아요'라고 하면 found=False."""
    llm = _FixedLLM("해당 정보는 아직 등록되어 있지 않아요.")
    res = await _ask("학식 메뉴 뭐야", llm, retriever, campus_data)
    assert res.found is False


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
    msg = build_user_message(hits, "q", max_chars=1)
    assert f"[{hits[0].doc.id}]" in msg and f"[{hits[1].doc.id}]" not in msg
