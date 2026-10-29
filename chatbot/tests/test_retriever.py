import pytest

from app.retriever.keyword import KeywordRetriever, tokenize
from app.schemas import CampusData


@pytest.fixture
def retriever(campus_data: CampusData) -> KeywordRetriever:
    """픽스처 데이터로 만든 검색기."""
    return KeywordRetriever(list(campus_data.facilities.values()))


def _top(retriever: KeywordRetriever, q: str) -> str | None:
    """최상위 결과 id."""
    hits = retriever.search(q)
    return hits[0].doc.id if hits else None


def test_tokenize_strips_particles() -> None:
    """끝 조사를 떼고 특수문자를 지운다."""
    assert tokenize("정보관은 어디에 있어요?") == ["정보관", "어디", "있어요"]


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("정보관 어디 있어?", "bld_jeongbo"),
        ("컴소과 사무실", "dept_cs"),
        ("학식 몇시까지 해요", "fac_cafeteria"),
        ("밥 먹을 데", "fac_cafeteria"),
        ("장학금 문의", "admin_welfare"),
    ],
)
def test_alias_match(retriever: KeywordRetriever, q: str, expected: str) -> None:
    """이름·별칭이 포함되면 찾는다."""
    assert _top(retriever, q) == expected


@pytest.mark.parametrize(
    ("q", "expected"),
    [("정보괸 어디", "bld_jeongbo"), ("학생시당 언제 열어", "fac_cafeteria")],
)
def test_typo_match(retriever: KeywordRetriever, q: str, expected: str) -> None:
    """한 글자 오타도 자모 퍼지 매칭으로 찾는다."""
    hit = retriever.search(q)[0]
    assert (hit.doc.id, hit.matched_by) == (expected, "fuzzy")


def test_longer_alias_wins(retriever: KeywordRetriever) -> None:
    """'전기자동차과'는 '전기'(전기과 별칭)보다 길게 일치한 전기자동차과가 1위."""
    assert _top(retriever, "전기자동차과 사무실") == "dept_ev"


@pytest.mark.parametrize("q", ["오늘 날씨 어때?", "너 이름이 뭐야", "주차장 어디야", "???"])
def test_unrelated_returns_empty(retriever: KeywordRetriever, q: str) -> None:
    """관련 없는 질문은 빈 결과."""
    assert retriever.search(q) == []


def test_two_char_alias_does_not_cross_words(retriever: KeywordRetriever) -> None:
    """'간호학 사무실'을 붙여 쓴 '학사'로 다른 문서가 잡히지 않는다."""
    assert retriever.search("간호학가 사무실") == []  # 픽스처엔 간호학과가 없다
