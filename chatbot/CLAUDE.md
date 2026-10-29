# CLAUDE.md — DIT NOW RAG

> 이 파일은 Claude Code가 가장 먼저 읽는 **메인 가이드**입니다.
> 세부 구현 규칙은 `SKILL/` 폴더에 기능별로 나뉘어 있습니다.
> **기능을 개발하기 전, 아래 "SKILL 라우팅 표"에서 해당 문서를 반드시 먼저 읽고 작업하세요.**

---

## 1. 프로젝트 개요

- **서비스명**: DIT NOW (동의과학대학교 AI 스마트 캠퍼스 서비스)
- **이 저장소의 역할**: 학생의 자연어 질문(예: "정보관 어디 있어?", "학생식당 몇 시까지 해?")에
  **교내 데이터(JSON)를 근거로** 답하는 RAG 백엔드.
  로그인한 학생에게는 개인 질문("내 다음 수업 어디야?", "졸업학점 몇 남았어?")도 답합니다(현재 목업 데이터).
- **동작 흐름**
  ```
  사용자 질문 (+ 로그인 토큰, + 직전 대화 history)
     → (−1) 후속 질문이면 대화 맥락으로 완전한 질문으로 재작성
     → (0) 의도 분류: 키워드 규칙 → (놓치면) LLM 보조
           교내 정보 | 다음 수업 | 요일별 시간표 | 수강 과목 | 성적 | 시험 | 남은 졸업학점
     → (1) 질문 정규화 (별칭/오타 처리)
     → (2) 교내 정보면 JSON 검색 (Retriever), 개인 질문이면 학생 데이터로 계산
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
| DB | MariaDB 11.4 (Docker) + SQLAlchemy 2.0 async (`aiomysql`), 테스트는 SQLite 메모리 |
| 설정 | `.env` + `pydantic-settings` |
| 테스트 | pytest |
| 포맷/린트 | ruff (format + lint) |

---

## 3. 디렉터리 구조

```
ditnow-rag/
├── CLAUDE.md                 # ← 지금 이 파일
├── SKILL/                    # 기능별 세부 가이드
├── data/                     # 교내 데이터 JSON (원본)
│   ├── facilities.json       # 검색 대상 (건물·학과·행정·편의시설·식당)
│   ├── buildings.json        # 건물 주소·좌표
│   └── mock/                 # DB 시드용 학생·강의·수강이력·졸업기준 목업
├── app/
│   ├── main.py               # FastAPI 진입점
│   ├── config.py             # 환경설정
│   ├── schemas.py            # Pydantic 모델 (데이터 + API)
│   ├── data_loader.py        # JSON 로드·검증
│   ├── models.py             # DB 테이블 (SQLAlchemy ORM)
│   ├── db.py                 # DB 연결·테이블 생성·시드
│   ├── student_repo.py       # DB → 처리기용 학생 정보 (취득 학점 계산)
│   ├── auth.py               # 학번 로그인·DB 토큰 세션
│   ├── intents.py            # 질문 의도 분류
│   ├── personal.py           # 개인 질문 처리기 (시간표·학점 계산)
│   ├── retriever/
│   │   ├── base.py
│   │   └── keyword.py        # (임베딩 검색은 아직 없음)
│   ├── llm/
│   │   ├── __init__.py       # get_llm_client 팩토리
│   │   ├── base.py           # LLMClient 인터페이스
│   │   ├── openai_client.py
│   │   ├── anthropic_client.py
│   │   └── fake_client.py    # 테스트 전용
│   ├── prompt.py             # 프롬프트 템플릿
│   └── rag.py                # 파이프라인 조립
├── scripts/
│   ├── eval.py               # 검색·답변 품질 평가
│   └── seed_db.py            # DB 테이블 생성·목업 시드
├── tests/
├── reports/                  # 평가 결과
├── docker-compose.yml        # MariaDB
├── .env.example
├── pyproject.toml            # ruff·pytest 설정
└── requirements.txt
```

---

## 4. SKILL 라우팅 표 ⭐

작업 내용에 맞는 문서를 **먼저 읽고** 그 규칙을 따르세요.

| 이런 작업을 할 때 | 읽을 문서 |
|---|---|
| JSON 데이터 구조 정의·추가·수정, `data_loader.py` | `SKILL/data-schema.md` |
| 검색 로직, 별칭·오타 처리, 임베딩 | `SKILL/retrieval.md` |
| 외부 LLM 연결, 공급자 추가·교체 | `SKILL/llm-client.md` |
| 프롬프트 작성, 답변 톤·형식, 환각 방지 | `SKILL/prompt.md` |
| API 엔드포인트, React 연동, CORS | `SKILL/api-server.md` |
| 테스트 작성, 답변 품질 평가 | `SKILL/testing.md` |
| 개인 질문(시간표·성적·시험·학점), 의도 분류, 로그인·카카오 연동 | `SKILL/student-assistant.md` |
| DB 테이블·쿼리·시드, MariaDB·Docker | `SKILL/database.md` |

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
7. **학생 식별은 로그인 토큰으로만** 하고, 개인 질문 답변은 캐시·로그에 남기지 않습니다.

---

## 6. 개발 명령어

```bash
# 가상환경 & 설치 (python3.11이 없으면: uv venv -p 3.11 .venv)
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# DB (MariaDB, Docker) — 서버 시작 시 테이블 생성·목업 시드
docker compose up -d
python scripts/seed_db.py --reset  # 목업을 고친 뒤 다시 넣기

# 서버 실행
uvicorn app.main:app --reload --port 8000

# LLM 없이 띄워 보기 (FakeLLMClient)
LLM_PROVIDER=fake uvicorn app.main:app --reload --port 8000

# 테스트 / 포맷 / 린트 / 검색 평가
pytest -q
ruff format . && ruff check . --fix
python scripts/eval.py            # --with-llm: 실제 LLM으로 환각 체크 (비용 발생)
```

---

## 7. 작업 진행 방식 (Claude Code용)

1. 요청을 받으면 **SKILL 라우팅 표**에서 관련 문서를 읽는다.
2. 변경할 파일과 접근 방식을 짧게 설명한 뒤 구현한다.
3. 구현 후 `pytest`와 `ruff check`를 실행해 통과를 확인한다.
4. 새 규칙이나 결정이 생기면 해당 `SKILL/*.md`를 함께 업데이트한다.
