from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.schemas import Facility


class SearchHit(BaseModel):
    """검색 결과 한 건."""

    doc: Facility
    score: float  # 0.0 ~ 1.0 (높을수록 관련)
    matched_by: str  # "alias" | "fuzzy" | "keyword"


class Retriever(ABC):
    """모든 검색기가 따르는 인터페이스."""

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        """질문과 관련된 문서를 점수순으로 반환한다."""
