import re
import unicodedata

from rapidfuzz import fuzz

from ..retriever.base import Retriever, SearchHit
from ..schemas import Facility

_NON_WORD = re.compile(r"[^0-9a-z가-힣]+")
_PARTICLE = re.compile(r"(에서|으로|은|는|이|가|을|를|에|로|도)$")
FUZZY_THRESHOLD = 85
NAME_WEIGHT = 0.7
KEYWORD_WEIGHT = 0.3


def normalize(text: str) -> str:
    """소문자화하고 특수문자를 공백으로 바꾼다."""
    return _NON_WORD.sub(" ", text.lower()).strip()


def tokenize(text: str) -> list[str]:
    """정규화된 질문을 단어로 나누고 끝 조사를 잘라낸다."""
    out = []
    for tok in normalize(text).split():
        stripped = _PARTICLE.sub("", tok)
        out.append(stripped if len(stripped) >= 2 else tok)
    return out


def _jamo(text: str) -> str:
    """한글을 자모로 분해한다. '정보괸'과 '정보관'처럼 음절 하나가 다른 오타를 가깝게 만든다."""
    return unicodedata.normalize("NFD", text)


def _contains(name: str, compact: str, tokens: list[str]) -> bool:
    """이름이 질문에 들어 있는지. 짧은 이름일수록 엄격하게 본다(오탐 방지)."""
    if len(name) >= 3:
        return name in compact  # 띄어쓰기 차이 허용: '컴소과 건물' == '컴소과건물'
    if len(name) == 2:
        return any(name in t for t in tokens)  # '간호학 사무실'의 '학사'처럼 단어를 넘는 매칭 금지
    return name in tokens  # '밥', '약'은 단어 전체가 같을 때만


class _Entry:
    """검색용으로 미리 전처리한 문서."""

    def __init__(self, doc: Facility) -> None:
        self.doc = doc
        self.names = [
            n for n in (normalize(x).replace(" ", "") for x in [doc.name, *doc.aliases]) if n
        ]
        # 2음절 이하 이름의 퍼지 매칭은 '학식'↔'학사'처럼 오탐이 많아 3음절 이상만 쓴다
        self.names_jamo = [_jamo(n) for n in self.names if len(n) >= 3]
        self.search_text = normalize(doc.to_search_text()).replace(" ", "")


class KeywordRetriever(Retriever):
    """별칭 정확 매칭 + 자모 퍼지 매칭 + 키워드 포함 비율로 점수를 매기는 검색기."""

    def __init__(self, docs: list[Facility], min_score: float = 0.35) -> None:
        self.entries = [_Entry(d) for d in docs]
        self.min_score = min_score

    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        """질문과 관련된 문서를 점수순으로 반환한다."""
        tokens = tokenize(query)
        compact = "".join(tokens)
        if not compact:
            return []
        # 퍼지 비교 대상: 각 단어 + 붙여 쓸 수 있는 인접 두 단어 ('도서관 열람싫' → '도서관열람싫')
        pairs = [a + b for a, b in zip(tokens, tokens[1:], strict=False)]
        candidates = [_jamo(c) for c in [*tokens, *pairs]]

        scored: list[tuple[float, int, SearchHit]] = []
        for e in self.entries:
            exact = [n for n in e.names if _contains(n, compact, tokens)]
            if exact:
                name_score, matched_by = 1.0, "alias"
            else:
                # 이름 전체 대 단어 전체로 비교해야 '유학생'이 '학생시당'에 부분 일치하지 않는다
                ratio = max((fuzz.ratio(n, c) for n in e.names_jamo for c in candidates), default=0)
                if ratio < FUZZY_THRESHOLD:
                    continue
                name_score, matched_by = ratio / 100, "fuzzy"
            keyword = sum(t in e.search_text for t in tokens) / len(tokens)
            score = NAME_WEIGHT * name_score + KEYWORD_WEIGHT * keyword
            if score >= self.min_score:
                # 동점이면 더 길게 일치한 이름이 우선 ('전기'보다 '전기자동차과')
                longest = max((len(n) for n in exact), default=0)
                scored.append(
                    (
                        score,
                        longest,
                        SearchHit(doc=e.doc, score=round(score, 3), matched_by=matched_by),
                    )
                )

        # 정확히 맞은 이름이 있으면 오타 보정 결과는 노이즈일 뿐이다
        if any(hit.matched_by == "alias" for _, _, hit in scored):
            scored = [s for s in scored if s[2].matched_by == "alias"]
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [hit for _, _, hit in scored[:top_k]]
