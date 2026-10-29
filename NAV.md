# DIT NOW — Repository Navigation Map

> 상태: 이 문서는 2026-10-29 현재 작업 트리의 실제 경로를 확인한 **탐색용 지도**다. 폴더를 옮기거나 코드를 변경하면 근거를 확인하고 갱신한다.
> 모든 작업은 아래 경로를 단서로 실제 파일을 확인해야 한다. 경로가 존재한다는 사실이 기능 완성을 의미하지는 않는다.

## 1. 제품과 문서 기준
- 전체 서비스 목표: 실제 학교 시스템을 참조하되 외부 내부 API에 의존하지 않는 **신규 통합 캠퍼스 플랫폼**. 학생·교수·조교·학과 대표·운영자 역할 포함.
- `README.md`의 AI 지도/길찾기는 제품 제안, `mvp/`의 브라우저 시연은 현재 구현 범위다. 전체 통합 캠퍼스 방향과 구체적 우선순위는 **`docs/11_DECISION_LOG.md`에서 확정 사항을 검증**한다.
- 문서 진입: `docs/00_START_HERE.md`; 제품: `docs/01_PRD.md`; 기능: `docs/02_FRD.md`; 비기능: `docs/03_NFR.md`; 권한: `docs/04_POLICY_RBAC.md`; 데이터: `docs/05_DATA_MODEL.md`; 아키텍처: `docs/06_ARCHITECTURE.md`; UX: `docs/07_IA_UX.md`; 테스트: `docs/08_TEST_QA.md`; 단계: `docs/09_RELEASE_SCOPE.md`; AI 워크플로: `docs/10_AI_RUNBOOK.md`; 결정: `docs/11_DECISION_LOG.md`; 심사: `docs/12_HACKATHON_GATE.md`; 학교 조사: `docs/13_EXISTING_SERVICE_AUDIT.md`; 전체 기준: `docs/15_PLATFORM_BASELINE.md`.
- 공식 조사 근거는 `docs/research/`의 조사 산출물 11개(기능 CSV 포함)를 본다. AI 환경 점검은 별도 `docs/research/09_AI_DEVELOPMENT_ENVIRONMENT.md`를 본다.
- 통합 설계 초안은 `docs/v1-draft/`의 PRD→FRD→NFR→RBAC→DB/API→아키텍처→IA/UX→QA 순으로 읽고, 92개 ID의 기능별 연결은 `docs/v1-draft/09_FEATURE_TRACEABILITY.csv`에서 확인한다. 미확정 정책은 `docs/v1-draft/11_OPEN_POLICIES_ASSUMPTIONS.md`를 따른다. 이 초안은 기존 확정 결정을 대체하지 않는다.
- P0 인증·학과/학년·익명 글·실명 모집·개인 기회의 FastAPI 서버/DB 후보/RLS 계약은 `docs/v1-draft/13_P0_SERVER_DB_RLS_CONTRACT.md`를 본다. 프런트 React/Vite/Tailwind와 FastAPI는 DEC-015 확정이며 실제 백엔드 구현·DB/인증·호스팅/비용 결정은 별개다.
- AI 개발 준비 점검과 실제 명령 결과는 `docs/dev-prep/01_READINESS_REVIEW.md`를 본다.

## 2. 현재 코드 진입점
| 영역 | 현재 경로 | 확인할 내용 |
| --- | --- | --- |
| React/Vite 앱 | `mvp/package.json`, `mvp/src/main.tsx`, `mvp/src/app/` | 앱 진입·라우트·권한 표시 |
| 학생 홈·시간표 | `mvp/src/features/home/` | 현재 학생 UI |
| 로그인 UI | `mvp/src/features/auth/` | 시연 인증 UI |
| 학과 채팅 | `mvp/src/features/department/` | 소속 채널 및 메시지 UI |
| 학교·학과 공지 | `mvp/src/features/notices/` | 담당자 공지·조회 UI |
| 익명·모집 커뮤니티 | `mvp/src/features/community/` | 익명 글·팀원 모집 UI |
| 장학·기회 | `mvp/src/features/opportunities/` | 지원 정보·체크리스트 UI |
| 공통 UI·타입 | `mvp/src/shared/ui/`, `mvp/src/shared/types.ts` | 공통 컴포넌트·계약 |
| 모의 API | `mvp/src/shared/data/api/` | 현재 브라우저 기반 규칙; 서버 아님 |
| 모의 저장소·시드 | `mvp/src/shared/data/store.ts`, `mvp/src/shared/data/seed.ts` | localStorage 및 테스트 데이터 |
| 별도 RAG 시연 서버 | `chatbot/app/main.py`, `chatbot/CLAUDE.md`, `chatbot/requirements.txt` | PR #14의 RAG/개인 질문/시연 세션·DB 코드. 통합 P0 인증·DB 계약과 연결은 미검증 |

**현재 중요한 한계:** `mvp/`는 localStorage + sessionStorage 기반 프런트 프로토타입이다. 서버 DB·인증·RLS·실시간 원격 채팅·실시간 화면 공유가 완성되었다고 주장하지 않는다. 백엔드는 실제 코드와 배포 여부를 다시 확인해야 한다.

FastAPI 공개 상태 확인 기반은 `services/api/app/main.py`에서 시작한다. 설정·공통 오류·안전 로그는 `services/api/app/core/`, 테스트는 `services/api/tests/`, 실행·잠금 파일 안내는 `services/api/README.md`를 본다. `/health`는 프로세스 생존만 확인하며 인증·DB 준비 상태는 검사하지 않는다. 작업 상태와 후속 게이트는 `docs/dev-prep/03_BACKEND_PROGRESS.md`에 기록한다.

`chatbot/`과 `services/api/`는 각각 별도 `app` 패키지이므로 각 디렉터리에서 독립 환경으로 실행·검증한다. RAG의 MariaDB 어댑터·자체 세션 코드는 플랫폼 DB·인증 공급자 선정의 승인 근거가 아니다. 이 기반 작업에서 RAG의 외부 LLM·DB·배포는 실행하지 않았다.

## 3. 현재 도구와 제안된 모노레포 영역
- 현재 `scripts/check-agent-config.mjs`: 탐색 경로와 스킬 구조 검사.
- 현재 `.github/workflows/mvp-ci.yml`: PR/main의 Node.js 22 MVP 설치·타입·빌드 검증.
- 현재 `.agents/skills/`: Codex 프로젝트 스킬 8개.
- 현재 `.claude/skills/`: Claude Code 프로젝트 스킬 8개 (동기화 복사본).
- 현재 `services/api/`: FastAPI 공개 health·공통 오류·설정·로그·테스트 기반. 제안 경로 (아직 없음): `apps/web/` (검증 후 웹 이전), `packages/contracts/` (OpenAPI 기반 공유 계약), `infra/db/migrations/` (DB 채택 후). 현재 `mvp/`는 보존한다.

**주의:** DEC-015는 프런트와 FastAPI만 확정한다. PostgreSQL은 권장 후보이며 인증·DB·호스팅·비용은 OPEN-002/003에 남는다.

## 4. 작업 유형별 먼저 읽을 자료
- 대학 사이트 조사: `docs/13_EXISTING_SERVICE_AUDIT.md`, `docs/15_PLATFORM_BASELINE.md`, `docs/research/`.
- 기능 기획/정합성: `docs/11_DECISION_LOG.md`, `docs/v1-draft/02_FRD.md`, `docs/v1-draft/09_FEATURE_TRACEABILITY.csv`, `docs/v1-draft/11_OPEN_POLICIES_ASSUMPTIONS.md`.
- 프런트 UI: 해당 기능의 `mvp/src/features/`, 공통 `mvp/src/shared/ui/`, `docs/v1-draft/07_IA_UX.md`.
- 인증/권한/익명/공식 채널: `docs/v1-draft/04_RBAC.md`, `docs/v1-draft/03_NFR.md`, `mvp/src/shared/data/api/core.ts`.
- DB/API 신규 구현: `docs/v1-draft/05_DB_API.md`, `docs/v1-draft/06_ARCHITECTURE.md`, `docs/v1-draft/04_RBAC.md`; 기존 mock과 서버를 혼동하지 않는다.
- 릴리스/QA: `docs/v1-draft/08_TEST_QA.md`, `docs/09_RELEASE_SCOPE.md`, `docs/12_HACKATHON_GATE.md`.

## 5. 현재 확인된 검증 명령
- `cd mvp && npm ci`
- `cd mvp && npm run typecheck`
- `cd mvp && npm run build`
- `node scripts/check-agent-config.mjs`
- `cd services/api` 후 `uv sync --locked`, `uv run --locked ruff check .`, `uv run --locked ruff format --check .`, `uv run --locked pytest` (Python 3.13·uv 0.13.6)
- GitHub Actions: `.github/workflows/mvp-ci.yml`에서 Node.js 22로 위 MVP 3명령 실행
- 현재 `mvp/package.json`에는 테스트·lint 명령이 없다. 존재하지 않는 명령을 실행했다고 주장하지 않는다. 추가 시 문서화한다.

## 6. NAV 갱신 규칙
- 폴더/파일 이동, 새 서비스 추가, 공통 계약 변경, 태스크 탐색 경로 변경 시 수정한다.
- 기능별 세부 로직을 여기로 복사하지 않는다. 1~2단계 안내 + 정확한 링크/경로만 유지한다.
- 검증하지 않은 경로를 '구현됨'으로 표시하지 않는다.
