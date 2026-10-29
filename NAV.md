# DIT NOW — Repository Navigation Map

> 상태: 2026-10-30. 현재 경로와 별도 브랜치의 작업 중 경로를 구별하는 **탐색용 지도**다.
> 모든 작업은 아래 경로를 단서로 실제 파일을 확인해야 한다. 경로가 존재한다는 사실이 기능 완성을 의미하지는 않는다.

## 1. 제품과 문서 기준
- 전체 서비스 목표: 실제 학교 시스템을 참조하되 외부 내부 API에 의존하지 않는 **신규 통합 캠퍼스 플랫폼**. 학생·교수·조교·학과 대표·운영자 역할 포함.
- DEC-016~018: MariaDB 확정, RAG는 공통 사용자·학적 기반 통합 기능, 신규 프런트 별도 작성. `mvp/`는 사전 프로토타입으로 최종 서비스·시연·제출 및 소스 복사 대상에서 제외한다.
- 문서 진입: `docs/00_START_HERE.md`; 제품: `docs/01_PRD.md`; 기능: `docs/02_FRD.md`; 비기능: `docs/03_NFR.md`; 권한: `docs/04_POLICY_RBAC.md`; 데이터: `docs/05_DATA_MODEL.md`; 아키텍처: `docs/06_ARCHITECTURE.md`; UX: `docs/07_IA_UX.md`; 테스트: `docs/08_TEST_QA.md`; 단계: `docs/09_RELEASE_SCOPE.md`; AI 워크플로: `docs/10_AI_RUNBOOK.md`; 결정: `docs/11_DECISION_LOG.md`; 심사: `docs/12_HACKATHON_GATE.md`; 학교 조사: `docs/13_EXISTING_SERVICE_AUDIT.md`; 전체 기준: `docs/15_PLATFORM_BASELINE.md`.
- 공식 조사 근거는 `docs/research/`의 조사 산출물 11개(기능 CSV 포함)를 본다. AI 환경 점검은 별도 `docs/research/09_AI_DEVELOPMENT_ENVIRONMENT.md`를 본다.
- 통합 설계 초안은 `docs/v1-draft/`의 PRD→FRD→NFR→RBAC→DB/API→아키텍처→IA/UX→QA 순으로 읽고, 92개 ID의 기능별 연결은 `docs/v1-draft/09_FEATURE_TRACEABILITY.csv`에서 확인한다. 미확정 정책은 `docs/v1-draft/11_OPEN_POLICIES_ASSUMPTIONS.md`를 따른다. 이 초안은 기존 확정 결정을 대체하지 않는다.
- P0 인증·소속·CRUD 계약은 `docs/v1-draft/13_P0_SERVER_DB_RLS_CONTRACT.md`, MariaDB 정정과 독립 보안 리뷰는 [승인 대기 PR #13](https://github.com/not-a-devs/ditNow/pull/13)을 본다. DB 제품 확정과 인증·운영 접속·비용 승인은 별개다.
- 전체 92개 1차 구현의 FE·BE·DB·테스트 상태는 `docs/dev-prep/06_FEATURE_IMPLEMENTATION_STATUS.csv`, Codex·Claude worktree·브랜치·파일 소유자는 `docs/dev-prep/05_PARALLEL_IMPLEMENTATION_BOARD.md`다.
- AI 개발 준비 점검과 실제 명령 결과는 `docs/dev-prep/01_READINESS_REVIEW.md`를 본다.

## 2. 현재 코드 진입점
| 영역 | 현재 경로 | 확인할 내용 |
| --- | --- | --- |
| 사전 React/Vite 프로토타입 | `mvp/package.json`, `mvp/src/main.tsx`, `mvp/src/app/` | 보존 전용; 아래 MVP 경로는 최종 구현 진척에서 제외 |
| 학생 홈·시간표 | `mvp/src/features/home/` | 현재 학생 UI |
| 로그인 UI | `mvp/src/features/auth/` | 시연 인증 UI |
| 학과 채팅 | `mvp/src/features/department/` | 소속 채널 및 메시지 UI |
| 학교·학과 공지 | `mvp/src/features/notices/` | 담당자 공지·조회 UI |
| 익명·모집 커뮤니티 | `mvp/src/features/community/` | 익명 글·팀원 모집 UI |
| 장학·기회 | `mvp/src/features/opportunities/` | 지원 정보·체크리스트 UI |
| 공통 UI·타입 | `mvp/src/shared/ui/`, `mvp/src/shared/types.ts` | 공통 컴포넌트·계약 |
| 모의 API | `mvp/src/shared/data/api/` | 현재 브라우저 기반 규칙; 서버 아님 |
| 모의 저장소·시드 | `mvp/src/shared/data/store.ts`, `mvp/src/shared/data/seed.ts` | localStorage 및 테스트 데이터 |
| 통합 대상 RAG | `chatbot/app/main.py`, `chatbot/CLAUDE.md`, `chatbot/requirements.txt` | 기존 RAG 재사용; 별도 시연 로그인은 최종 공통 세션으로 대체. 통합 연결은 브랜치 작업 중 |

**현재 중요한 한계:** `mvp/`는 localStorage + sessionStorage 기반 프런트 프로토타입이다. 서버 DB·인증·RLS·실시간 원격 채팅·실시간 화면 공유가 완성되었다고 주장하지 않는다. 백엔드는 실제 코드와 배포 여부를 다시 확인해야 한다.

FastAPI 공개 상태 확인 기반은 `services/api/app/main.py`에서 시작한다. 설정·공통 오류·안전 로그는 `services/api/app/core/`, 테스트는 `services/api/tests/`, 실행·잠금 파일 안내는 `services/api/README.md`를 본다. `/health`는 프로세스 생존만 확인하며 인증·DB 준비 상태는 검사하지 않는다. 작업 상태와 후속 게이트는 `docs/dev-prep/03_BACKEND_PROGRESS.md`에 기록한다.

실제 공개 API 스냅샷은 `services/api/openapi.json`, 내보내기/드리프트 검사는 `services/api/app/export_openapi.py`다. 프런트 타입은 `mvp/scripts/api-types.mjs`로 `mvp/src/shared/api/schema.d.ts`에 생성한다. 제안 상태의 인증·도메인 API는 스냅샷에 추가하지 않는다.

현재 main의 `chatbot/`과 `services/api/`는 각각 `app` 패키지여서 독립 환경이 필요하다. F 작업이 패키지 import와 공개 검색을 단계적으로 통합한다. DB 선택 근거는 사용자 DEC-016이며 기존 demo 세션은 공통 인증 승인 근거가 아니다. 외부 LLM·실DB·배포는 미검증이다.

## 3. 현재 도구와 제안된 모노레포 영역
- 현재 `scripts/check-agent-config.mjs`: 탐색 경로와 스킬 구조 검사.
- 현재 `.github/workflows/mvp-ci.yml`: 사전 프로토타입 보존 회귀; 최종 앱 완료 증거 아님.
- 현재 `.github/workflows/python-api-ci.yml`: PR/main의 Python 3.13 잠금 설치·Ruff·pytest·앱 import/OpenAPI 생성·에이전트 설정 검사. 두 워크플로가 같은 PR HEAD에서 성공해야 한다.
- 현재 `.agents/skills/`: Codex 프로젝트 스킬 8개.
- 현재 `.claude/skills/`: Claude Code 프로젝트 스킬 8개 (동기화 복사본).
- 현재 `services/api/`: FastAPI 공개 health·공통 오류·설정·로그·테스트 기반.
- 현재 `scripts/check-feature-progress.mjs`: 92개 FR 집합·중복·계층 상태·TC/DB/RBAC 연결 검사.
- 별도 작업 브랜치: `apps/web/` 신규 작성, 공통 MariaDB 모델/인증 dependency, feature별 API/UI 및 RAG adapter. main 구현으로 집계하지 않는다. 브랜치와 소유 범위는 병렬 보드를 본다.

**주의:** MariaDB는 확정이다. 클라우드 접속·인증·호스팅/비용·관리자 권한은 OPEN-002/003 게이트를 유지한다.

## 4. 작업 유형별 먼저 읽을 자료
- 대학 사이트 조사: `docs/13_EXISTING_SERVICE_AUDIT.md`, `docs/15_PLATFORM_BASELINE.md`, `docs/research/`.
- 기능 기획/정합성: `docs/11_DECISION_LOG.md`, `docs/v1-draft/02_FRD.md`, `docs/v1-draft/09_FEATURE_TRACEABILITY.csv`, `docs/v1-draft/11_OPEN_POLICIES_ASSUMPTIONS.md`.
- 신규 프런트 UI: B 작업 브랜치의 apps/web과 `docs/v1-draft/07_IA_UX.md`. mvp 구현 참조·복사 금지.
- 인증/권한/익명/공식 채널: `docs/v1-draft/04_RBAC.md`, `docs/v1-draft/03_NFR.md`, 승인 대기 PR #13과 A 작업 브랜치. 프로토타입 API는 보안 권위가 아니다.
- DB/API 신규 구현: `docs/v1-draft/05_DB_API.md`, `docs/v1-draft/06_ARCHITECTURE.md`, `docs/v1-draft/04_RBAC.md`; 기존 mock과 서버를 혼동하지 않는다.
- 릴리스/QA: `docs/v1-draft/08_TEST_QA.md`, `docs/09_RELEASE_SCOPE.md`, `docs/12_HACKATHON_GATE.md`.

## 5. 현재 확인된 검증 명령
- `cd mvp && npm ci`
- `cd mvp && npm run typecheck`
- `cd mvp && npm run build`
- `node scripts/check-agent-config.mjs`
- `node scripts/check-feature-progress.mjs`
- `cd services/api` 후 `uv sync --locked`, `uv run --locked ruff check .`, `uv run --locked ruff format --check .`, `uv run --locked pytest` (Python 3.13·uv 0.13.6)
- GitHub Actions: `.github/workflows/mvp-ci.yml`에서 Node.js 22로 위 MVP 3명령 실행
- 현재 `mvp/package.json`에는 테스트·lint 명령이 없다. 존재하지 않는 명령을 실행했다고 주장하지 않는다. 추가 시 문서화한다.

## 6. NAV 갱신 규칙
- 폴더/파일 이동, 새 서비스 추가, 공통 계약 변경, 태스크 탐색 경로 변경 시 수정한다.
- 기능별 세부 로직을 여기로 복사하지 않는다. 1~2단계 안내 + 정확한 링크/경로만 유지한다.
- 검증하지 않은 경로를 '구현됨'으로 표시하지 않는다.
