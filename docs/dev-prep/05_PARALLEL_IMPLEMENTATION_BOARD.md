# DIT NOW 병렬 구현 보드

2026-10-30 KST · TASK-ORCH-92 · 기준 main `a86ec597`.
fullstack-implementation·nav-doc-maintenance 적용. 관련 전체 FR 92개, NFR-SEC/PRIV/REL/UX/OPS 및 각 TC-V1은 [기능 추적표](../v1-draft/09_FEATURE_TRACEABILITY.csv)에서 연결한다.

## 목표와 완료 판단

전체 92개를 1차 구현 대상으로 관리한다. 로그인·실DB 핵심 3 CRUD·보안·배포가 최우선이며 독립 P1/P2를 병렬 진행한다. P0 완료가 개발 종료 조건은 아니다. 전체 가능한 구현 → 전체 자동 검사 → 사용자 직접 검사 → 보완·재기획을 반복한다.

[92행 상태표](06_FEATURE_IMPLEMENTATION_STATUS.csv)는 main의 기능 상태다. 브랜치의 작업 중 코드나 사전 mvp를 main 완료율로 집계하지 않는다. 최초 기준은 모두 운영 통합 미검증이다. 기존 chatbot의 시설 조회 코드는 PARTIAL 2행(상위 CAMP-001과 세부 CAMP-003)이며 두 독립 완성 기능을 뜻하지 않는다. 나머지는 NOT_IMPLEMENTED 또는 운영 정책 BLOCKED이며 각 세부 계층은 NOT_RUN이다.

| 상태 | 필요한 증거 |
|---|---|
| NOT_IMPLEMENTED | 최종 앱에 구현 없음; 계약/문서만 있음 |
| PARTIAL | FE/BE/DB 중 일부 코드만 존재; 실제 연결 미완료 |
| BLOCKED | 운영 정책/외부 접근/환경/필수 승인 미충족; 안전한 시연 별도 가능 |
| IMPLEMENTED | 필요한 FE/BE/MariaDB 연결 코드 존재; 아직 전체 검증 전 |
| VERIFIED (별도 계층) | 해당 환경의 TC·2계정·영속성·오류·회귀 증거와 HEAD/실행 기록 필요 |

문서 DOCUMENTED, 단위 TESTED, 운영 VERIFIED는 다른 사실이다. 조회 전용 공개 원문은 MariaDB N_A 사유를 쓰고 검증된 출처 스냅샷으로 가능하다. 내부 규정 미확인을 실제 학교 정책으로 만들지 않는다.

## 실행 중인 격리 작업

각 worktree는 `C:/DIT CSW/` 아래다. root는 아래와 다른 기존 작업/미커밋 파일을 건드리지 않는다. Claude CLI 2.1.312의 기존 인증을 사용하며 권한 우회·추가 비용 서비스 개설은 하지 않는다.

| 태스크/세션 | worktree · 브랜치 | 소유 파일 | 현재 상태/차단 |
|---|---|---|---|
| A · Codex pr11_independent_review | ditNow-p0-domain-contracts · feat/p0-provider-neutral-contracts-20261030 | services/api/app/db/**, schemas/p0.py·operations.py, api/dependencies.py, 공통 DB repositories, pyproject/uv.lock, auth/DB tests | 구현 중. 45개 체크포인트 테스트. Docker daemon 미실행·클라우드 접속 없음. 인증/DB 보안 PR은 사람 승인 전 병합 금지 |
| B · Codex api_foundation_review | ditNow-web-shell · feat/new-platform-web-shell-20261030 | apps/web 공통 셸·라우터·디자인·lib·테스트·패키지, 아래 feature 디렉터리 제외 | 신규 작성 중. mvp 코드를 읽거나 복사하지 않음 |
| C · Claude CLI | ditNow-community · feat/community-recruitment-firstpass-20261030 | app/features/community/**, test_community*.py, apps/web/src/features/community/**, TASK_COMMUNITY_IMPLEMENTATION.md | 실제 CLI 시작. 익명/실명 서비스·입력·UI, 공통 인증/DB 통합 대기 |
| D · Claude CLI | ditNow-opportunities · feat/opportunity-firstpass-20261030 | app/features/opportunities/**, test_opportunities*.py, apps/web/src/features/opportunities/**, TASK_OPPORTUNITIES_IMPLEMENTATION.md | 실제 CLI 시작. 공고·개인 준비, 공통 인증/DB 통합 대기 |
| E · Claude CLI | ditNow-campus · feat/campus-communication-firstpass-20261030 | app/features/campus/**, test_campus*.py, apps/web/src/features/campus/**, TASK_CAMPUS_IMPLEMENTATION.md | 실제 CLI 시작. 대상 범위·공지 단일 원본/카드 계약·채팅, 실제 실시간/학적 승인 대기 |
| F · Codex rag_integration | ditNow-rag-integration · feat/integrated-rag-adapter-20261030 | chatbot 패키징/상대 import, integrations/chatbot/**, schemas/ai.py, api/v1/ai.py, test_chatbot_integration*.py | 공개 검색 어댑터/기존 회귀 검증 중. 개인 학적·LLM 외부 호출 차단 |
| ORCH · root | ditNow-orchestration · docs/integrated-mariadb-roadmap-20261030 | 결정/NAV/README/아키텍처/로드맵/진행표/검사 스크립트, 후속 공통 router·CI 통합 | 전체 92개·공통 계약·PR/CI 조정 |

`app/` 약칭은 services/api/app/이다. 모든 PR 제목/본문/커밋은 한국어. 각 작업은 테스트 후 PR로 전달하고 root가 독립 검토·HEAD CI를 확인한다. 동일 파일 수정 금지. 마이그레이션/인증/공통 의존성은 A 단일 소유이며 F 로컬 패키지 의존성은 A 작업 후 root가 통합한다.

## 최소 공통 계약

- FastAPI 실제 `schemas/common.py`가 성공/오류 권위다. data/resource_version/server_time, 오류 code/message/field_errors/retryable/request_id. 아직 구현하지 않은 경로를 OpenAPI 실행 경로로 표시하지 않는다.
- 인증 공급자 미설정은 fail closed. 검증된 외부 issuer/subject→내부 UUID, 현재 소속·역할/소유권은 서버 원장에서 재검사한다. 테스트 fake는 tests 안에만 두고 운영 로그인으로 표시하지 않는다.
- MariaDB 최소 GRANT/제약/트랜잭션+FastAPI 범위 질의. PostgreSQL 네이티브 RLS와 SET LOCAL을 MariaDB 기능처럼 적용하지 않는다. 브라우저 DB 직접 접근 금지.
- B의 신규 frontend `src/lib/api.ts`: requestData<T>(path, init?)는 data 반환, ApiError에 code/status/requestId. feature `src/features/{community,opportunities,campus,ai}/index.tsx`는 default React component. 모듈이 아직 병합되지 않았으면 미구현 안내만 표시한다.
- C/D/E는 자기 서비스·입출력·repository Protocol·주입형 router를 작성한다. 공유 인증을 우회하여 임시 공개 CRUD를 열지 않는다. 실제 DB adapter와 통합 테스트 전 VERIFIED 금지.
- 공지 원본 한 건→대상 카드 참조, 외부 장학 제출은 자체 신고. 익명 공개 모델에 개인 식별자/소속/감사 상관값을 넣지 않는다.

## 후속 배정과 통합 순서

1. A 모델/인증 제안·B 신규 셸·F 공개 RAG를 독립 검증한다. A는 보안 승인 PR로 보류하고 B/F의 비보호 경로는 회귀·CI 성공 시 병합 가능하다.
2. C/D/E 단위 결과를 공통 계약과 대조한 뒤 별도 PR로 검토한다. DB 스키마 요청은 A에게 모으고 실제 권한 경계 병합은 승인 후 진행한다.
3. 공통 계약 승인·MariaDB 접속 준비 후 가상 로그인→핵심 3 CRUD FE/BE/DB 영속성→2계정 권한→통합/배포를 우선 검증한다.
4. 비어 있는 세션은 같은 파일을 피하여 강의실·과제·질문·출결 시연, 도서/예약, 입학 공개 안내·가상 흐름 등 진행표의 P1/P2 항목을 순서대로 배정한다. 정책 필요한 처리 대신 허용된 공개 안내부터 구현한다.
5. 가능한 전체를 자동 검사하고 사용자 직접 검수용 시나리오·환경·가상 계정을 준비한다. 사용자 승인 없이 유료 개통/배포/운영 관리자 생성 금지.

## 진행과 차단 증거

- PR #11 사용자 병합 확인: 5d08cb4d4cd92ea06dbe5404b69e894eb0a0822a.
- [PR #13](https://github.com/not-a-devs/ditNow/pull/13): Claude CLI 독립 설계 리뷰 및 MariaDB/통합 원장 정정. HEAD ea3ff0b8c2b9b413080690bb9f2b27a6a4d01632의 CI 성공. 사람 보안 승인 대기, 자동 병합 금지.
- PR #15 FastAPI 기반, #16 Python CI, #17 공개 OpenAPI·타입 검사는 main 병합 완료. 업무 로그인/CRUD/MariaDB 완료를 뜻하지 않는다.
- Docker 실행 파일은 있으나 desktop-linux daemon pipe가 없어 MariaDB 통합 검사는 NOT_RUN. 클라우드 연결·비밀키·예산·인증 방식·시연 관리자 책임은 미확정이다.
- Claude 세션 결과는 세션 종료 후 변경 범위/커밋/PR/검사 로그로 갱신한다. 실행 시작 사실을 성공/완료로 표시하지 않는다. AI 리뷰는 사람 공식 승인이 아니다.

수용 기준: 진행표 ID=명세 92개 집합, 중복 없음, 모든 행 계층/우선순위/차단/후속 태스크·TC 추적, mvp 완료율 제외, 공통 파일 충돌 없음. 자동 검사: `node scripts/check-feature-progress.mjs`, `node scripts/check-agent-config.mjs`, `git diff --check`.
