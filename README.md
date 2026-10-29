# 🏫 DIT NOW

> **동의과학대학교 구성원을 위한 통합 대학 플랫폼**<br>
> "학교의 모든 정보를 내 손안에서, 더욱 간편하고 편리하게"

> **현재 상태 (2026-10-30)**
> - 신규 통합 웹(`apps/web`)과 통합 API(`services/api`)는 구현·자동 테스트를 마쳤습니다.
> - 통합 API에 연결된 기능: **학번 로그인**, **AI 답변(RAG + LLM, 교내·개인 질문)**, **AI 시설 검색**, **대학·학과 안내**, health 확인. 학번 로그인과 AI 답변은 팀 MariaDB(Tailscale 경유)와 실제 LLM으로 동작을 확인했습니다.
> - 신규 웹에 연결된 화면: 통합 홈·10개 메뉴, AI 시설 검색, 대학·학과 안내. **AI 답변·로그인 화면은 아직 웹에 연결 전**입니다(API만 제공).
> - 커뮤니티·기회·학과·강의실·도서관·입학·생활지원 기능은 **화면·API 모듈과 테스트가 있지만 아직 통합 앱에 연결 전**입니다.
> - 배포는 진행 중입니다. 학생·성적 데이터는 모두 **가상(목업) 데이터**입니다.
> - 92개 기능의 화면·API·DB·테스트 상태는 [기능 진행표](docs/dev-prep/06_FEATURE_IMPLEMENTATION_STATUS.csv)에서 따로 추적합니다.

<br>

## 📌 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 서비스명 | DIT NOW |
| 대상 | 학생·교수·조교·학과 대표·운영자 등 대학 구성원 |
| 개발 기간 | 2026.10.29 ~ 30 (해커톤) |
| 한 줄 소개 | 학사·학과 소통·강의실·협업·기회·학생지원·AI를 하나의 계정으로 연결하는 통합 캠퍼스 플랫폼 |

### 문제 정의
- 캠퍼스 건물·시설이 많아 **처음 오는 학생은 강의실·편의시설 위치를 찾기 어렵습니다.**
- 학사 일정, 공지, 장학, 도서관, 학과 소통이 **여러 사이트와 앱에 흩어져 있어** 필요한 정보를 빠르게 찾기 힘듭니다.

### 해결 방법
- 학생이 **평소 말투 그대로 질문**하면 AI가 의도를 이해하고 교내 데이터에 근거해 답합니다. 모르는 내용은 지어내지 않습니다.
- 학교 기능을 **10개 메뉴로 묶은 하나의 웹 앱**에서 학생·교직원이 같은 계정으로 이용합니다.
- 실제 학교 시스템을 참고하되 학교 내부 API에 의존하지 않는 **신규 독립 플랫폼**으로 만듭니다.

### 시스템 구조

```
 [브라우저]
    │
    ▼
 apps/web  (React 신규 통합 웹, 10개 메뉴 탐색)
    │  HTTP /api/v1
    ▼
 services/api  (FastAPI 통합 API: 공통 응답·오류·로그)
    ├─ /api/v1/health
    ├─ /api/v1/auth/login·logout   학번 로그인 (DB 토큰 세션)
    ├─ /api/v1/ai/ask ─────────┐   의도 분류 → 검색/학적 계산 → LLM 답변
    ├─ /api/v1/ai/campus/search ┴─▶ chatbot  (RAG 패키지 재사용, 코드 복제 없음)
    ├─ /api/v1/public-campus        대학·학과 안내
    └─ features/* 모듈 (커뮤니티·기회·학과·강의실·도서관·입학·생활지원, 연결 전)
    │
    ▼  Tailscale 사설망 :3307
 MariaDB 11.4  (팀원 Proxmox VM, infra/mariadb)
    ├─ ditnow          공통 플랫폼 DB (사용자·권한, 가상 학적·로그인 세션)
    └─ ditnow_chatbot  챗봇 데이터 영역
```

### 폴더 구조

| 경로 | 내용 |
|---|---|
| `apps/web/` | 신규 통합 웹 (React + TypeScript + Vite + Tailwind) |
| `services/api/` | 통합 FastAPI 서버와 기능 모듈 (`app/features/*`) |
| `chatbot/` | RAG 챗봇 (검색기·의도 분류·LLM 답변·평가 스크립트) |
| `infra/mariadb/` | 공용 MariaDB 서버의 Compose·계정·백업 스크립트 (비밀값 미포함) |
| `docs/` | PRD·FRD·NFR·권한·데이터 모델·아키텍처·결정 기록 |
| `.agents/skills/`, `.claude/skills/` | AI 에이전트용 프로젝트 스킬 8종 |
| `mvp/` | 사전 프로토타입 (보존 전용, 최종 서비스·시연·제출 대상 아님) |

자세한 탐색 지도는 [NAV.md](NAV.md)를 참고하세요.

<br>

## ✨ 주요 기능

### 1. 🤖 캠퍼스 AI 도우미 (RAG)
- **교내 정보 질문:** "정보관 어디 있어?", "학생식당 몇 시까지 해?"처럼 물으면 건물·학과 사무실·행정부서·편의시설·식당의 위치, 전화번호, 운영시간을 교내 데이터에서 찾아 답합니다.
  - 별칭(컴소과, 긱사, 과사)과 한 글자 오타(정보괸, 학생시당)도 알아듣습니다.
  - 데이터에 없는 내용은 "아직 등록되어 있지 않아요"라고 답하고 문의처를 안내합니다.
- **개인 질문 (로그인, 가상 학적 데이터):** 다음 수업 위치, 요일별 시간표, 수강 과목·교수, 성적·평점, 시험 일정과 D-day, 졸업까지 남은 학점.
  - 학점·평점·날짜 계산은 **코드가 하고**, LLM은 확정된 사실을 문장으로만 바꿉니다.
- **후속 질문:** 직전 대화를 보고 "거기 몇 시까지 해?"를 완전한 질문으로 바꿔 답합니다.
- **의도 분류:** 키워드 규칙을 먼저 적용하고, 규칙에 없는 표현만 LLM이 분류합니다.
- **연결 상태:** 통합 API `POST /api/v1/ai/ask`로 교내·개인 질문 모두 답합니다(학번 로그인 후 개인 질문). 신규 웹 `/app/ai`에는 현재 **공개 시설 검색** 화면만 연결되어 있습니다.

### 2. 🧭 통합 캠퍼스 홈과 10개 메뉴
- 캠퍼스 홈 · 학사·시간표 · 내 강의실 · 우리 학과 · 익명 커뮤니티 · 팀원 모집 · 장학·기회 · 학생 지원 · 대학·학과 안내 · AI 도우미
- **대학·학과 안내**는 공식 근거 기반 요약의 목록·검색·필터·상세를 통합 API와 웹에 연결했습니다.
- 모바일·데스크톱 반응형, 키보드 이동, 로딩·실패·재시도 상태를 공통으로 처리합니다.

### 3. 🧩 업무 기능 모듈 (구현·테스트 완료, 통합 앱 연결 전)
| 영역 | 기능 |
|---|---|
| 우리 학과 | 학과·학년 채팅, 공식 공지 카드, 학사 일정 |
| 익명 커뮤니티 · 팀원 모집 | 익명 게시글, 실명 팀원 모집 |
| 장학 · 기회 | 장학금·공모전·취업 정보, 저장과 준비 체크리스트 |
| 내 강의실 | 강의 조회, 교수에게 질문, 과제 |
| 학생 지원 (도서관) | 도서 검색, 대출 연장, 희망도서 신청, 공간 예약 |
| 입학 | 입학 안내, 가상 지원서 작성 |
| 생활 · 학생지원 | 생활 지원 가상 신청, 본인 신청 조회 |

### 4. 🗄 공용 MariaDB 서버
- 팀원 서버의 VM에 Docker로 MariaDB 11.4를 운영합니다. 인터넷에 포트를 열지 않고 Tailscale 사설망으로만 접속합니다.
- 플랫폼 DB와 챗봇 DB, 앱·마이그레이션·챗봇·백업 계정을 분리했습니다. 매일 백업 스크립트를 포함합니다.

<br>

## 🛠 기술 스택

| 분류 | 기술 |
|---|---|
| Frontend | React 19, TypeScript 5.9, Vite 8, Tailwind CSS 4, Vitest + Testing Library, openapi-typescript (API 타입 자동 생성) |
| Backend | Python 3.13, FastAPI, Pydantic v2, uv (잠금 설치), Ruff, pytest |
| AI · RAG | 키워드·별칭·자모 오타 검색(RapidFuzz), LLM 의도 분류·답변 생성 (OpenAI / OpenAI 호환 학교 서버 / Anthropic 중 `.env`로 선택) |
| Database | MariaDB 11.4.13 (utf8mb4), SQLAlchemy async + aiomysql. 원격 읽기·직접 GRANT 확인, 엄격 async TLS는 CA/SAN 대기 |
| Infra | Docker Compose, Proxmox VM (Ubuntu 24.04), Tailscale 사설망 |
| CI | GitHub Actions: 신규 웹, Python API, 챗봇, 프로토타입 검증 워크플로 4개 |
| 개발 도구 | Claude Code, Codex, Git / GitHub |

학번 로그인 선택은 DEC-020에 기록되어 있지만 공통 UUID·현재 권한·실DB 연결 완료를 뜻하지 않습니다. 원격 migration·CRUD 쓰기·백업은 미검증이며 인증서 검증을 해제하지 않습니다. 통합 API는 `DIT_API_` 환경 변수를 사용하고 `.env`를 자동으로 읽지 않습니다. 기존 standalone 챗봇 설정과 구분하며 [현재 DB 검사](docs/dev-prep/07_DB_CONNECTIVITY_AND_ROLES.md)를 따릅니다.

<br>

## 🚀 실행 방법

### 1. 저장소 클론
```bash
git clone https://github.com/not-a-devs/ditNow
cd ditNow
```

### 2. 통합 API 서버 (`services/api`)
Python 3.13과 [uv](https://docs.astral.sh/uv/)가 필요합니다.
```bash
cd services/api
uv sync --locked
export DIT_API_ENVIRONMENT=development
export DIT_API_DOCS_ENABLED=true
export DIT_API_CORS_ORIGINS='["http://localhost:5181"]'
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```
- http://127.0.0.1:8000/docs 에서 API를 확인합니다.
- 시설 검색 예: `GET /api/v1/ai/campus/search?q=컴소과&limit=5`
- 앱은 `.env`를 자동으로 읽지 않습니다. 설정 키 설명은 `services/api/.env.example`에 있습니다.

**학번 로그인과 AI 답변까지 켜려면** DB와 LLM 설정을 추가합니다. 비밀번호·API 키는 화면과 쉘 기록에 남지 않게 입력하세요.
```bash
# 1) 처음 한 번: 테이블 생성 + 가상 학적 시드 (migration 계정)
export DIT_API_DATABASE_URL='mysql+aiomysql://ditnow_migrator:<URL인코딩한_PW>@<tailscale-ip>:3307/ditnow?charset=utf8mb4'
uv run --locked python -m app.seed_demo

# 2) 서버 실행 (앱 계정 + LLM)
export DIT_API_DATABASE_URL='mysql+aiomysql://ditnow_app:<URL인코딩한_PW>@<tailscale-ip>:3307/ditnow?charset=utf8mb4'
export DIT_API_LLM_PROVIDER=openai_compatible DIT_API_LLM_MODEL=<모델> DIT_API_LLM_BASE_URL=<주소>
read -rs DIT_API_LLM_API_KEY && export DIT_API_LLM_API_KEY
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```
- `/docs`에서 `POST /api/v1/auth/login`에 가상 계정 `20231001` / `3000001`로 로그인 → **Authorize**에 토큰 입력 → `POST /api/v1/ai/ask`에 `{"question": "내 다음 수업 어디야?"}`.
- DB 설정이 없으면 로그인·개인 질문만 503이고, LLM 설정이 없으면 `/ai/ask`만 503입니다. 나머지 API는 그대로 동작합니다.

### 3. 신규 통합 웹 (`apps/web`)
Node.js 22.12 이상이 필요합니다.
```bash
cd apps/web
npm ci
echo 'VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1' > .env.local
npm run dev -- --port 5181
```
- http://127.0.0.1:5181/app 에서 통합 홈을 엽니다. `/app/ai`에서 시설 검색을 써 볼 수 있습니다.

### 4. RAG 챗봇 단독 실행 (`chatbot`, 개발·평가용)
통합 API와 별도로 챗봇만 띄워 볼 때 씁니다. Python 3.11 이상, LLM API 키, MariaDB 접속 정보가 필요합니다.
```bash
cd chatbot
uv sync --locked --all-extras
cp .env.example .env    # LLM_PROVIDER, LLM_MODEL, LLM_API_KEY, DATABASE_URL 설정
uv run --locked --all-extras uvicorn app.main:app --reload
```
- http://localhost:8000/docs 에서 `/auth/login`으로 가상 계정 `20231001` / `3000001`에 로그인한 뒤 `/ask`에 질문합니다.
- LLM 없이 흐름만 볼 때는 `LLM_PROVIDER=fake`로 실행합니다.
- 자세한 내용은 [chatbot/README.md](chatbot/README.md)와 `chatbot/SKILL/`을 참고하세요.

### 5. 테스트
```bash
cd apps/web && npm test && npm run build
cd services/api && uv run --locked ruff check . && uv run --locked pytest
cd chatbot && uv run --locked --all-extras pytest -q
```

> DB 접속 정보·비밀번호는 저장소에 포함하지 않습니다. 공용 MariaDB 접속은 [infra/mariadb/README.md](infra/mariadb/README.md)와 [DB 연결 안내](docs/dev-prep/07_DB_CONNECTIVITY_AND_ROLES.md)를 따르세요.

<br>

## 🧠 AI 활용 내역

### 1. 서비스 안의 AI — 캠퍼스 RAG 도우미
| 항목 | 내용 |
|---|---|
| 방식 | 검색 증강 생성(RAG): 질문과 관련된 교내 데이터를 먼저 찾고, 그 내용만 근거로 LLM이 답변 |
| 데이터 | 교내 시설 82건, 건물 16동 (`chatbot/data/`), 가상 학생 3명·강의 42개·수강 61건·시험 13건 (`chatbot/data/mock/`) |
| 모델 | `.env`로 교체 가능: OpenAI, OpenAI 호환 학교 자체 서버, Anthropic Claude |
| 환각 방지 | 근거가 없으면 LLM을 호출하지 않음 · 답변의 근거 id를 검증 · 숫자 계산은 코드가 수행 · 모르는 내용은 "등록되어 있지 않아요" |
| 개인정보 | 학번은 서버가 검증한 로그인 토큰에서만 읽음 · 교내 질문에는 학적을 읽지 않음 · 개인 답변은 캐시하지 않음 · 질문 로그에 학번 미저장 |
| 품질 평가 | 실제 학생 말투 평가 질문 95개 (`chatbot/scripts/eval.py`): 교내 검색 Recall@3 51/51, 실제 LLM 2회 연속 개인·후속 질문 51/51, 환각 0건 |
| 제공 경로 | 통합 API `POST /api/v1/ai/ask` (챗봇 패키지를 그대로 호출, 학번 로그인 연동). 요청 제한 IP당 분당 20회 |

**처리 흐름**
```
질문 (+ 직전 대화)
 → 후속 질문이면 완전한 질문으로 재작성 (LLM)
 → 의도 분류: 키워드 규칙 → 놓치면 LLM 보조
 → 교내 질문: 시설 데이터 검색 / 개인 질문: DB에서 학적 조회 후 코드로 계산
 → LLM 답변 생성 → 근거 검증 → 답변 + 근거 + 위치
```

### 2. 개발 과정의 AI 활용
| 도구 | 활용 내용 |
|---|---|
| Claude Code | RAG 챗봇 설계·구현·테스트, 평가 질문 작성과 오분류 수정, MariaDB 서버 구성과 운영 스크립트, 코드 리뷰, 문서 작성 |
| Codex | 신규 통합 웹·통합 API·기능 모듈의 병렬 구현, 독립 리뷰와 결함 수정 |
| 프로젝트 스킬 8종 | 요구사항 격차 검토, 구현 계획, 풀스택 구현, 권한·개인정보 리뷰, UX 점검, 출시 게이트, 학교 공식 사이트 조사, 문서 동기화를 AI 에이전트가 같은 기준으로 수행 (`.agents/skills/`, `.claude/skills/`) |
| AI 작업 규칙 | 사람이 목표·정책·병합을 결정하고, AI는 기획·설계·구현·리뷰·QA 역할로 나눠 작업 ([AI 런북](docs/10_AI_RUNBOOK.md), [결정 기록](docs/11_DECISION_LOG.md)) |

- 인증 방식, 성적 판정 규칙, 공식 학교 표시처럼 보안·정책에 영향을 주는 결정은 AI가 임의로 확정하지 않고 사람이 결정합니다.

<br>

## 👥 팀원 역할

| 이름 | 역할 | 담당 업무 |
|---|---|---|
| 안성해 | 팀장 / PM / 백엔드 | 기획, 발표, 데이터 가공, RAG 챗봇 구성, MariaDB 서버 구성 |
| 김정현 | Frontend | React UI 개발, 화면 설계 |
| 이동원 | Backend | API 명세서 작성, 문서 정리 |
| 최민재 | Data / Network | 데이터 수집 및 정리, 네트워크 환경 개선 |

<br>
