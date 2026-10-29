# SKILL: 테스트 & 품질 평가

> 대상 파일: `tests/`

## 1. 테스트 구성

```
tests/
├── conftest.py             # 테스트용 데이터·FakeLLMClient 픽스처
├── fixtures/               # 작은 테스트용 JSON
├── test_data.py            # 스키마 검증, id 중복, 깨진 참조
├── test_retriever.py       # 별칭·오타·무관 질문
├── test_rag.py             # 파이프라인 (FakeLLMClient 사용)
├── test_api.py             # FastAPI TestClient로 엔드포인트
└── eval_questions.json     # 답변 품질 평가 세트
```

## 2. 규칙

- **`pytest`는 실제 LLM API를 절대 호출하지 않습니다.** 항상 `FakeLLMClient`를 주입합니다.
- 테스트는 `data/` 원본이 아닌 `tests/fixtures/`의 작은 데이터를 씁니다. 단, `test_data.py`는 실제 `data/`도 검증합니다.
- 버그를 고치면 그 버그를 재현하는 테스트를 먼저 추가합니다.

## 3. 품질 평가 세트 (`eval_questions.json`)

```json
[
  { "question": "정보관 어디 있어?",     "expect_ids": ["fac-info-hall"], "expect_found": true },
  { "question": "컴소과 건물 위치",       "expect_ids": ["fac-info-hall"], "expect_found": true },
  { "question": "학식 몇시까지 해요",     "expect_ids": ["sch-cafeteria"], "expect_found": true },
  { "question": "학교 수영장 어디야?",    "expect_ids": [],                "expect_found": false }
]
```

- 실제 학생들이 할 법한 말투로 작성합니다 (반말, 줄임말, 오타 포함).
- 데이터를 추가할 때마다 질문도 2~3개씩 추가합니다.

## 4. 평가 스크립트 (`scripts/eval.py`)

- **검색 평가 (API 비용 없음)**: 각 질문의 검색 결과 상위 3개에 `expect_ids`가 포함되는지 → `Recall@3` 출력
- **답변 평가 (실제 LLM 사용, 수동 실행)**: `python scripts/eval.py --with-llm`
  - `expect_found=false` 질문에 "등록되어 있지 않아요"로 답했는지 (환각 체크)
  - `sources`에 `expect_ids`가 들어 있는지
- 결과는 `reports/eval_YYYYMMDD.md`로 저장해 이전 결과와 비교합니다.

## 5. 완료 기준

- [ ] `pytest -q` 전부 통과
- [ ] `ruff check .` 경고 없음
- [ ] 검색 `Recall@3` ≥ 0.9
- [ ] 없는 정보 질문에 대한 환각 0건
