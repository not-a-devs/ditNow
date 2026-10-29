# CLAUDE.md — DIT NOW RAG

> 이 파일은 Claude Code가 가장 먼저 읽는 **메인 가이드**입니다.
> 세부 구현 규칙은 `SKILLS/` 폴더에 기능별로 나뉘어 있습니다.
> **기능을 개발하기 전, 아래 "SKILLS 라우팅 표"에서 해당 문서를 반드시 먼저 읽고 작업하세요.**

---

## 1. 프로젝트 개요

- **서비스명**: DIT NOW (동의과학대학교 AI 스마트 캠퍼스 서비스)
- **이 저장소의 역할**: 학생의 자연어 질문(예: "정보관 어디 있어?", "학생식당 몇 시까지 해?")에
  **교내 데이터(JSON)를 근거로** 답하는 RAG 백엔드
- **동작 흐름**
  ```
  사용자 질문
     → (1) 질문 정규화 (별칭/오타 처리)
     → (2) JSON 데이터에서 관련 문서 검색 (Retriever)
     → (3) 검색 결과 + 질문으로 프롬프트 구성
     → (4) 외부 LLM 호출
     → (5) 답변 + 근거(출처 ID, 좌표 등) 반환
  ```
- **프론트엔드**: React + Tailwind 앱이 이 서버의 HTTP API를 호출합니다.

---

## 2. 기술 스택

| 구분 | 선택 |
|---|---|
| 언어 | **Python 3.11** (3.12+ 문법 사용 금지) |
| API 서버 | FastAPI + Uvicorn |
| 데이터 검증 | Pydantic v2 |
| 검색 | 키워드/별칭 매칭(rapidfuzz) + 선택적 임베딩 검색 |
| LLM | 외부 API (공급자 교체 가능하도록 추상화) |
| 설정 | `.env` + `pydantic-settings` |
| 테스트 | pytest |
| 포맷/린트 | ruff (format + lint) |

---

## 3. 디렉터리 구조

```
ditnow-rag/
├── CLAUDE.md                 # ← 지금 이 파일
├── SKILLS/                   # 기능별 세부 가이드
├── data/                     # 교내 데이터 JSON (원본)
│   ├── facilities.json
│   ├── schedules.json
│   └── faq.json
├── app/
│   ├── main.py               # FastAPI 진입점
│   ├── config.py             # 환경설정
│   ├── schemas.py            # Pydantic 모델 (데이터 + API)
│   ├── data_loader.py        # JSON 로드·검증
│   ├── retriever/
│   │   ├── base.py
│   │   ├── keyword.py
│   │   └── embedding.py      # (선택)
│   ├── llm/
│   │   ├── base.py           # LLMClient 인터페이스
│   │   ├── openai_client.py
│   │   ├── anthropic_client.py
│   │   └── fake_client.py    # 테스트 전용
│   ├── prompt.py             # 프롬프트 템플릿
│   └── rag.py                # 파이프라인 조립
├── scripts/
│   └── eval.py               # 검색·답변 품질 평가
├── tests/
├── .env.example
└── requirements.txt
```

---

## 4. SKILLS 라우팅 표 ⭐

작업 내용에 맞는 문서를 **먼저 읽고** 그 규칙을 따르세요.

| 이런 작업을 할 때 | 읽을 문서 |
|---|---|
| JSON 데이터 구조 정의·추가·수정, `data_loader.py` | `SKILLS/data-schema.md` |
| 검색 로직, 별칭·오타 처리, 임베딩 | `SKILLS/retrieval.md` |
| 외부 LLM 연결, 공급자 추가·교체 | `SKILLS/llm-client.md` |
| 프롬프트 작성, 답변 톤·형식, 환각 방지 | `SKILLS/prompt.md` |
| API 엔드포인트, React 연동, CORS | `SKILLS/api-server.md` |
| 테스트 작성, 답변 품질 평가 | `SKILLS/testing.md` |

여러 영역에 걸친 작업이면 관련 문서를 모두 읽으세요.

---

## 5. 절대 규칙

1. **근거 없는 답변 금지** — LLM은 검색된 JSON 내용만으로 답해야 합니다.
   데이터에 없으면 "해당 정보는 아직 등록되어 있지 않아요"라고 답합니다.
2. **API 키는 코드에 쓰지 않습니다** — 반드시 `.env`에서 읽고, `.env`는 커밋하지 않습니다.
3. **LLM 공급자에 직접 의존하지 않습니다** — 파이프라인은 항상 `LLMClient` 인터페이스만 사용합니다.
4. **데이터는 로드 시점에 Pydantic으로 검증**합니다. 스키마가 틀린 JSON은 서버 시작 시 에러로 알립니다.
5. **타입 힌트 필수**, 함수·클래스에는 짧은 한국어 docstring을 답니다.
6. 사용자 답변은 **한국어 존댓말**로 합니다.

---

## 6. 개발 명령어

```bash
# 가상환경 & 설치
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 서버 실행
uvicorn app.main:app --reload --port 8000

# 테스트 / 포맷 / 린트
pytest -q
ruff format . && ruff check . --fix
```

---

## 7. 작업 진행 방식 (Claude Code용)

1. 요청을 받으면 **SKILLS 라우팅 표**에서 관련 문서를 읽는다.
2. 변경할 파일과 접근 방식을 짧게 설명한 뒤 구현한다.
3. 구현 후 `pytest`와 `ruff check`를 실행해 통과를 확인한다.
4. 새 규칙이나 결정이 생기면 해당 `SKILLS/*.md`를 함께 업데이트한다.
