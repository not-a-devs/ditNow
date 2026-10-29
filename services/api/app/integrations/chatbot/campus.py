"""기존 검색기를 재사용하되 시연 인증·DB·LLM 런타임은 가져오지 않는다."""

from functools import lru_cache
from importlib.resources import as_file, files

from chatbot.app.data_loader import load_data
from chatbot.app.retriever.keyword import KeywordRetriever

from app.schemas.ai import CampusSearchData, CampusSearchHit


class CampusSearch:
    """개인 원장에 접근할 수 없는 읽기 전용 시설 검색 서비스."""

    def __init__(self, retriever: KeywordRetriever):
        self._retriever = retriever

    def search(self, query: str, limit: int) -> CampusSearchData:
        hits = self._retriever.search(query, top_k=limit)
        return CampusSearchData(
            found=bool(hits),
            hits=[
                CampusSearchHit(
                    source_id=hit.doc.id,
                    name=hit.doc.name,
                    category=hit.doc.category,
                    text=hit.doc.text,
                    building=hit.doc.building,
                    floor=hit.doc.floor,
                    room=hit.doc.room,
                    hours=hit.doc.hours,
                    score=hit.score,
                    matched_by=hit.matched_by,
                )
                for hit in hits
            ],
        )


@lru_cache(maxsize=1)
def get_campus_search() -> CampusSearch:
    """설치된 패키지의 공개 시설 JSON만 로드하고 검색 인덱스를 재사용한다."""
    with as_file(files("chatbot").joinpath("data")) as data_dir:
        campus = load_data(data_dir)
    return CampusSearch(KeywordRetriever(list(campus.facilities.values())))
