# SKILL: 검색 (Retriever)

> 대상 파일: `app/retriever/*.py`

## 1. 인터페이스

모든 검색기는 같은 인터페이스를 따릅니다. 파이프라인(`rag.py`)은 이 인터페이스만 사용합니다.

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from app.schemas import Facility

class SearchHit(BaseModel):
    doc: Facility
    score: float          # 0.0 ~ 1.0 (높을수록 관련)
    matched_by: str       # "alias" | "fuzzy" | "keyword"

class Retriever(ABC):
    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        """질문과 관련된 문서를 점수순으로 반환한다."""
```

## 2. 검색 단계 (기본: KeywordRetriever)

1. **정규화** — 소문자화, 특수문자 제거, 단어 끝 조사(`은/는/이/가/을/를/에/에서/로/으로/도`) 제거
   - 예: `"정보관은 어디에 있어요?"` → `["정보관", "어디", "있어요"]`
   - 형태소 분석기는 쓰지 않습니다(설치 부담).
2. **이름·별칭 정확 매칭** (`name_score=1.0`, `matched_by="alias"`) — 이름 길이별로 엄격도가 다릅니다.
   - 3음절 이상: 띄어쓰기를 무시하고 질문 전체에서 찾음 (`컴소과 건물` == `컴소과건물`)
   - 2음절: **한 단어 안에서만** 찾음 (`간호학 사무실`의 `학사` 오탐 방지)
   - 1음절(`밥`, `약`): 단어 전체가 같을 때만
3. **퍼지 매칭** — 정확 매칭이 없을 때, 3음절 이상 이름만 대상으로
   **자모 분해(`unicodedata` NFD) 후** 질문의 각 단어·인접 두 단어 결합과 `rapidfuzz.fuzz.ratio` ≥ 85 이면 후보 (`matched_by="fuzzy"`)
   - `partial_ratio`(부분 일치)는 쓰지 않습니다. `유학생`이 `학생시당`에 부분 일치하는 오탐이 생깁니다.
   - 음절 단위 비교로는 "정보괸"↔"정보관"이 67점이지만 자모로는 89점이 됩니다.
   - 어떤 문서든 정확 매칭이 있으면 퍼지 결과는 모두 버립니다.
4. **키워드 점수** — 질문 단어 중 `to_search_text()`에 포함된 비율
5. `score = 0.7 * name_score + 0.3 * keyword`, **`MIN_SCORE`(기본 0.35) 미만은 버립니다**.
   이름이 전혀 맞지 않으면 키워드만으로는 결과에 들어가지 않습니다.
6. 동점이면 더 길게 일치한 이름이 우선합니다 (`전기자동차과` 질문 → `전기`가 아닌 `전기자동차과`).

## 3. 연관 문서 확장

- 아직 구현하지 않았습니다. 시설의 `text`·`building`에 위치가 이미 들어 있어 필요성이 낮습니다.

## 4. 임베딩 검색 (선택, `embedding.py`)

- 키워드 검색으로 부족할 때만 추가합니다. 기본 비활성화 (`USE_EMBEDDING=false`).
- 임베딩은 **서버 시작 시 한 번 계산해 `data/.cache/embeddings.npy`에 캐시**합니다. JSON 파일이 바뀌면(해시 비교) 재계산.
- 하이브리드 점수: `final = 0.6 * keyword + 0.4 * embedding`
- 임베딩 API 호출도 `LLMClient`처럼 추상화하고, 키는 `.env`에서 읽습니다.

## 5. 금지 사항

- 검색 단계에서 LLM을 호출하지 않습니다 (속도·비용 문제).
- 데이터 전체를 프롬프트에 넣는 방식으로 검색을 대신하지 않습니다. 반드시 `top_k`로 자릅니다.

## 6. 테스트 포인트

- 별칭으로 정확히 찾아지는지 ("컴소과 사무실" → `dept_cs`)
- 오타 질문이 올바른 문서를 찾는지
- 관련 없는 질문("오늘 날씨 어때?")은 빈 결과가 나오는지
