# SKILL: 검색 (Retriever)

> 대상 파일: `app/retriever/*.py`

## 1. 인터페이스

모든 검색기는 같은 인터페이스를 따릅니다. 파이프라인(`rag.py`)은 이 인터페이스만 사용합니다.

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from app.schemas import BaseDoc

class SearchHit(BaseModel):
    doc: BaseDoc
    score: float          # 0.0 ~ 1.0 (높을수록 관련)
    matched_by: str       # "alias" | "keyword" | "embedding"

class Retriever(ABC):
    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        """질문과 관련된 문서를 점수순으로 반환한다."""
```

## 2. 검색 단계 (기본: KeywordRetriever)

1. **정규화** — 공백·특수문자 제거, 소문자화, 조사 일부 제거
   - 예: `"정보관은 어디에 있어요?"` → `"정보관 어디 있어요"`
   - 끝에 붙는 조사(`은/는/이/가/을/를/에/에서/로`)는 단순 규칙으로 잘라냅니다. 형태소 분석기는 쓰지 않습니다(설치 부담).
2. **별칭 정확 매칭** — 질문에 `name` 또는 `aliases`가 그대로 포함되면 `score=1.0`, `matched_by="alias"`
3. **퍼지 매칭** — `rapidfuzz.fuzz.partial_ratio`로 `name`/`aliases`와 비교, 80점 이상이면 후보
   - 오타 대응: "정보괸", "학생시당" 등
4. **키워드 점수** — `to_search_text()`에 질문 단어가 몇 개 포함되는지로 보조 점수
5. 점수 합산 후 `top_k`개 반환, **`MIN_SCORE`(기본 0.35) 미만은 버립니다**

## 3. 연관 문서 확장

- 상위 결과 문서에 `related_ids`나 `contains`가 있으면 해당 문서도 함께 가져옵니다 (점수 × 0.8).
- 예: "학식 몇 시까지?" → `sch-cafeteria` 매칭 → `fac-cafeteria`(위치)도 함께 전달

## 4. 임베딩 검색 (선택, `embedding.py`)

- 키워드 검색으로 부족할 때만 추가합니다. 기본 비활성화 (`USE_EMBEDDING=false`).
- 임베딩은 **서버 시작 시 한 번 계산해 `data/.cache/embeddings.npy`에 캐시**합니다. JSON 파일이 바뀌면(해시 비교) 재계산.
- 하이브리드 점수: `final = 0.6 * keyword + 0.4 * embedding`
- 임베딩 API 호출도 `LLMClient`처럼 추상화하고, 키는 `.env`에서 읽습니다.

## 5. 금지 사항

- 검색 단계에서 LLM을 호출하지 않습니다 (속도·비용 문제).
- 데이터 전체를 프롬프트에 넣는 방식으로 검색을 대신하지 않습니다. 반드시 `top_k`로 자릅니다.

## 6. 테스트 포인트

- 별칭으로 정확히 찾아지는지 ("컴소과 건물" → `fac-info-hall`)
- 오타 질문이 올바른 문서를 찾는지
- 관련 없는 질문("오늘 날씨 어때?")은 빈 결과가 나오는지
