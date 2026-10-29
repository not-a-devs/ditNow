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
├── test_llm.py             # LLM 팩토리·FakeLLMClient
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
  { "question": "정보괸 어딨음",         "expect_ids": ["bld_jeongbo"],   "expect_found": true },
  { "question": "컴소과 사무실 어디야",   "expect_ids": ["dept_cs"],       "expect_found": true },
  { "question": "학식 몇시까지 해요",     "expect_ids": ["fac_cafeteria"], "expect_found": true },
  { "question": "주차장 어디야",          "expect_ids": [],                "expect_found": false }
]
```

- 실제 학생들이 할 법한 말투로 작성합니다 (반말, 줄임말, 오타 포함).

### 개인 질문 평가 세트 (`eval_personal.json`)

```json
{ "student_id": "20231001", "question": "이따 수업 몇 시야?", "expect_intent": "next_class",
  "expect_ids": ["CS201"], "expect_text": ["10:00|10시"] }
```

- 기준 시각은 `scripts/eval.py`의 `EVAL_NOW`(2026-10-26 월 09:00 KST)로 고정합니다.
- `student_id: null`이면 비로그인 → `need_login=true`여야 통과입니다.
- `expect_text`는 답변에 반드시 들어가야 할 숫자·장소입니다. `|`로 같은 뜻의 다른 표기를 허용합니다.
- 키워드 목록에 없는 자연스러운 표현도 일부러 넣어 의도 분류의 빈틈을 찾습니다.
  키워드로는 못 잡고 LLM 분류가 있어야 맞히는 질문은 `"needs_llm": true` — LLM 없는 평가에서는 건너뜁니다.
- LLM 평가에서 답변 본문에 내부 id(`CS201` 등)가 보이면 실패로 기록합니다.
- 모델 답변은 실행마다 조금씩 달라집니다. 프롬프트를 바꾸면 `--with-llm`을 **두 번 이상** 돌려 확인하세요.
- 데이터를 추가할 때마다 질문도 2~3개씩 추가합니다.

## 4. 평가 스크립트 (`scripts/eval.py`)

- **검색 평가 (API 비용 없음)**: 각 질문의 검색 결과 상위 3개에 `expect_ids`가 포함되는지 → `Recall@3` 출력
  - 개인 질문은 FakeLLMClient로 의도 정확도·근거·로그인 요구를 확인합니다.
- **답변 평가 (실제 LLM 사용, 수동 실행)**: `python scripts/eval.py --with-llm`
  - `expect_found=false` 질문에 "등록되어 있지 않"이 들어 있는지 (환각 체크). 모른다고 밝힌 뒤 문의처를 덧붙이는 건 정상입니다.
  - 개인 질문 답변에 `expect_text`(계산된 숫자·장소)가 그대로 들어 있는지
  - `sources`에 `expect_ids`가 들어 있는지
- 결과는 `reports/eval_YYYYMMDD.md`(LLM 평가는 `_llm` 접미사)로 저장해 커밋하고, 이전 결과와 비교합니다.
- `Recall@3` < 0.9, 개인 질문 의도 정확도 < 0.9, 환각 또는 숫자·장소 불일치가 1건이라도 있으면 종료 코드 1을 반환합니다.
- `expect_found=false`인데 검색은 되는 질문(예: "학식 오늘 메뉴 뭐야")은 LLM이 거절해야 하는 환각 체크용입니다.

## 5. 완료 기준

- [ ] `pytest -q` 전부 통과
- [ ] `ruff check .` 경고 없음
- [ ] 검색 `Recall@3` ≥ 0.9
- [ ] 개인 질문 의도 정확도 ≥ 0.9
- [ ] 없는 정보 질문에 대한 환각 0건, 개인 질문 숫자·장소 불일치 0건
